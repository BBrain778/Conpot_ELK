# modified by Sooky Peter <xsooky00@stud.fit.vutbr.cz>
# Brno University of Technology, Faculty of Information Technology
import struct
import socket
import time
import logging
import sys
import codecs
import json  # 添加 JSON 日誌支持
from lxml import etree
from gevent.server import StreamServer

import modbus_tk.modbus_tcp as modbus_tcp
from modbus_tk import modbus

# Following imports are required for modbus template evaluation
import modbus_tk.defines as mdef
from conpot.core.protocol_wrapper import conpot_protocol
from conpot.protocols.modbus import slave_db
import conpot.core as conpot_core

logger = logging.getLogger(__name__)

@conpot_protocol
class ModbusServer(modbus.Server):

    def __init__(self, template, template_directory, args, timeout=5):

        self.timeout = timeout
        self.delay = None
        self.mode = None
        self.host = None
        self.port = None
        self.json_log_file = '/var/log/conpot/conpot.json'  # 設置 JSON 日誌文件路徑
        databank = slave_db.SlaveBase(template)

        # Constructor: initializes the server settings
        modbus.Server.__init__(
            self, databank if databank else modbus.Databank())

        # retrieve mode of connection and turnaround delay from the template
        self._get_mode_and_delay(template)

        # not sure how this class remember slave configuration across
        # instance creation, i guess there are some
        # well hidden away class variables somewhere.
        self.remove_all_slaves()
        self._configure_slaves(template)

    def _get_mode_and_delay(self, template):
        dom = etree.parse(template)
        self.mode = dom.xpath('//modbus/mode/text()')[0].lower()
        if self.mode not in ['tcp', 'serial']:
            logger.error('Conpot modbus initialization failed due to incorrect'
                         ' settings. Check the modbus template file')
            sys.exit(3)
        try:
            self.delay = int(dom.xpath('//modbus/delay/text()')[0])
        except ValueError:
            logger.error('Conpot modbus initialization failed due to incorrect'
                         ' settings. Check the modbus template file')
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
                    logger.debug(
                        'Added block %s to slave %s. '
                        '(type=%s, start=%s, size=%s)',
                        name, slave_id, request_type, start_addr, size)

            logger.info('Conpot modbus initialized')
        except Exception as e:
            logger.error(e)

    def log_to_json(self, event_data):
        """將事件記錄到 JSON 日誌文件"""
        try:
            # 將 bytes 轉換為字符串，避免序列化錯誤
            def convert_bytes(obj):
                if isinstance(obj, bytes):
                    return obj.decode('utf-8')
                if isinstance(obj, dict):
                    return {k: convert_bytes(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [convert_bytes(i) for i in obj]
                return obj
    
            event_data = convert_bytes(event_data)
    
            with open(self.json_log_file, 'a') as log_file:
                log_file.write(json.dumps(event_data) + '\n')
        except IOError as e:
            logger.error(f"Failed to write to JSON log file: {e}")
        except TypeError as e:
            logger.error(f"Failed to serialize JSON data: {e}")


    def handle(self, sock, address):
        sock.settimeout(self.timeout)

        session = conpot_core.get_session('modbus', address[0], address[1], sock.getsockname()[0], sock.getsockname()[1])

        self.start_time = time.time()
        logger.info(
            'New Modbus connection from %s:%s. (%s)',
            address[0], address[1], session.id)
        session.add_event({'type': 'NEW_CONNECTION'})

        try:
            while True:
                request = None
                try:
                    request = sock.recv(7)
                except Exception as e:
                    logger.error('Exception occurred in ModbusServer.handle() '
                                'at sock.recv(): %s', str(e))

                if not request:
                    logger.info('Modbus client disconnected. (%s)', session.id)
                    session.add_event({'type': 'CONNECTION_LOST'})
                    break
                if request.strip().lower() == 'quit.':
                    logger.info('Modbus client quit. (%s)', session.id)
                    session.add_event({'type': 'CONNECTION_QUIT'})
                    break
                if len(request) < 7:
                    logger.info('Modbus client provided data {} but invalid.'.format(session.id))
                    session.add_event({'type': 'CONNECTION_TERMINATED'})
                    break
                tr_id, pr_id, length = struct.unpack(">HHH", request[:6])
                while len(request) < (length + 6):
                    new_byte = sock.recv(1)
                    request += new_byte
                query = modbus_tcp.TcpQuery()

                response, logdata = self._databank.handle_request(
                    query, request, self.mode
                )
                logdata['request'] = codecs.encode(request, 'hex').decode('utf-8')
                logdata['src_ip'] = address[0]
                logdata['src_port'] = address[1]
                logdata['dst_ip'] = sock.getsockname()[0]
                logdata['dst_port'] = sock.getsockname()[1]

                # **🔍 記錄原本的 Modbus traffic**
                logger.info("Modbus traffic from %s: %s (%s)", address[0], logdata, session.id)

                # **🔍 檢查特定設備變更，新增 JSON 日誌**
                if logdata.get('function_code') in [mdef.WRITE_SINGLE_COIL, mdef.WRITE_MULTIPLE_COILS]:
                    event_message = None

                    # 🚦 **信號燈控制器 (Slave ID 3)**
                    if logdata.get('slave_id') == 3:
                        if logdata.get('starting_address') == 1:  # 紅燈
                            event_message = "Train Signal Change To RED" if logdata.get('response_value') == 1 else "Train Signal Change To GREEN"
                        elif logdata.get('starting_address') == 2:  # 綠燈
                            event_message = "Train Signal Change To GREEN" if logdata.get('response_value') == 1 else "Train Signal Change To RED"

                    # 🚧 **平交道控制器 (Slave ID 4)**
                    elif logdata.get('slave_id') == 4:
                        if logdata.get('starting_address') == 3:
                            event_message = "CLOSE CrossingBarrier" if logdata.get('response_value') == 1 else "OPEN CrossingBarrier"

                    # 🔀 **道岔控制器 (Slave ID 5)**
                    elif logdata.get('slave_id') == 5:
                        if logdata.get('starting_address') == 4:
                            event_message = "TrackPosition Switch To LEFT" if logdata.get('response_value') == 1 else "TrackPosition Switch To RIGHT"

                    # **記錄 JSON 日誌和終端機**
                    if event_message:
                        json_event = {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "event": event_message,
                            "slave_id": logdata.get('slave_id'),
                            "address": logdata.get('starting_address'),
                            "value": logdata.get('response_value'),
                            "function_code": logdata.get('function_code'),
                            "src_ip": logdata.get('src_ip'),
                            "src_port": logdata.get('src_port'),
                            "dst_ip": logdata.get('dst_ip'),
                            "dst_port": logdata.get('dst_port')
                        }
                        # **寫入 Conpot JSON 日誌**
                        self.log_to_json(json_event)
                        # **顯示在終端機**
                        logger.info("[Event] %s", json_event)

                if response:
                    sock.sendall(response)
                    logger.info('Modbus response sent to %s', address[0])
                else:
                    logger.info('Modbus client ignored due to invalid addressing. (%s)', session.id)
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
