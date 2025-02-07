import struct
import socket
import time
import logging
import sys
import codecs
import json  # JSON 日誌支持
import subprocess
from lxml import etree
from gevent.server import StreamServer

import modbus_tk.modbus_tcp as modbus_tcp
from modbus_tk import modbus

import modbus_tk.defines as mdef
from conpot.core.protocol_wrapper import conpot_protocol
from conpot.protocols.modbus import slave_db
import conpot.core as conpot_core

logger = logging.getLogger(__name__)

@conpot_protocol
class ModbusServer(modbus.Server):

    def __init__(self, template, template_directory, args, timeout=5):
        self.timeout = timeout
        self.host = None
        self.port = None
        self.json_log_file = '/var/log/conpot/conpot.json'  # JSON 日誌文件

        databank = slave_db.SlaveBase(template)
        modbus.Server.__init__(self, databank if databank else modbus.Databank())

        self._get_mode_and_delay(template)
        self.remove_all_slaves()
        self._configure_slaves(template)
        self.start_fake_shell()

    def _get_mode_and_delay(self, template):
        dom = etree.parse(template)
        self.mode = dom.xpath('//modbus/mode/text()')[0].lower()
        if self.mode not in ['tcp', 'serial']:
            logger.error('Conpot modbus initialization failed due to incorrect settings.')
            sys.exit(3)
        try:
            self.delay = int(dom.xpath('//modbus/delay/text()')[0])
        except ValueError:
            logger.error('Conpot modbus initialization failed due to incorrect settings.')
            sys.exit(3)

    def _configure_slaves(self, template):
        dom = etree.parse(template)
        slaves = dom.xpath('//modbus/slaves/*')
        try:
            for s in slaves:
                slave_id = int(s.attrib['id'])
                slave = self.add_slave(slave_id)
                logger.debug('Added slave with id %s.', slave_id)
                for b in s.xpath('./blocks/*'):
                    name = b.attrib['name']
                    request_type = eval('mdef.' + b.xpath('./type/text()')[0])
                    start_addr = int(b.xpath('./starting_address/text()')[0])
                    size = int(b.xpath('./size/text()')[0])
                    slave.add_block(name, request_type, start_addr, size)
                    logger.debug('Added block %s to slave %s. (type=%s, start=%s, size=%s)',
                                 name, slave_id, request_type, start_addr, size)

            logger.info('Conpot modbus initialized')
        except Exception as e:
            logger.error(e)

    def log_to_json(self, event_data):
        """記錄事件到 JSON 日誌"""
        try:
            with open(self.json_log_file, 'a') as log_file:
                log_file.write(json.dumps(event_data) + '\n')
        except IOError as e:
            logger.error(f"Failed to write to JSON log file: {e}")
        except TypeError as e:
            logger.error(f"Failed to serialize JSON data: {e}")

    def start_fake_shell(self):
        """ 啟動假 Shell 模擬 """
        subprocess.Popen(["python3", "fake_shell.py"])

    def handle(self, sock, address):
        sock.settimeout(self.timeout)
        session = conpot_core.get_session('modbus', address[0], address[1], sock.getsockname()[0], sock.getsockname()[1])

        self.start_time = time.time()
        logger.info('New Modbus connection from %s:%s. (%s)', address[0], address[1], session.id)
        session.add_event({'type': 'NEW_CONNECTION'})

        try:
            while True:
                request = None
                try:
                    request = sock.recv(7)
                except Exception as e:
                    logger.error('Exception in ModbusServer.handle(): %s', str(e))

                if not request:
                    logger.info('Modbus client disconnected. (%s)', session.id)
                    session.add_event({'type': 'CONNECTION_LOST'})
                    break

                tr_id, pr_id, length = struct.unpack(">HHH", request[:6])
                while len(request) < (length + 6):
                    request += sock.recv(1)
                
                query = modbus_tcp.TcpQuery()
                response, logdata = self._databank.handle_request(query, request, self.mode)

                logdata['request'] = codecs.encode(request, 'hex').decode('utf-8')
                logdata['src_ip'] = address[0]
                logdata['src_port'] = address[1]
                logdata['dst_ip'] = sock.getsockname()[0]
                logdata['dst_port'] = sock.getsockname()[1]

                # **🔍 記錄完整 Modbus traffic**
                logger.info("Modbus traffic from %s: %s (%s)", address[0], logdata, session.id)

                # **📌 記錄 JSON 日誌**
                json_event = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "event_type": "MODBUS_TRAFFIC",
                    "request": logdata.get('request'),
                    "slave_id": logdata.get('slave_id'),
                    "function_code": logdata.get('function_code'),
                    "src_ip": logdata.get('src_ip'),
                    "src_port": logdata.get('src_port'),
                    "dst_ip": logdata.get('dst_ip'),
                    "dst_port": logdata.get('dst_port'),
                    "response": codecs.encode(response, 'hex').decode('utf-8') if response else None
                }
                self.log_to_json(json_event)

                if response:
                    sock.sendall(response)
                    logger.info('Modbus response sent to %s', address[0])
                else:
                    logger.info('Invalid Modbus request. Closing connection. (%s)', session.id)
                    session.add_event({'type': 'CONNECTION_TERMINATED'})
                    sock.shutdown(socket.SHUT_RDWR)
                    sock.close()
                    break

        except socket.timeout:
            logger.debug('Socket timeout, remote: %s. (%s)', address[0], session.id)
            session.add_event({'type': 'CONNECTION_LOST'})

    def start(self, host, port):
        self.host = host
        self.port = port
        connection = (host, port)
        server = StreamServer(connection, self.handle)
        logger.info('Modbus server started on: %s', connection)
        server.start()
