import struct
from lxml import etree
import codecs
from modbus_tk.modbus import (
    Databank,
    DuplicatedKeyError,
    MissingKeyError,
    ModbusInvalidRequestError,
)
from modbus_tk import defines

from conpot.protocols.modbus.slave import MBSlave
import logging

logger = logging.getLogger(__name__)


class SlaveBase(Databank):
    """
    Database keeping track of the slaves.
    """

    def __init__(self, template):
        Databank.__init__(self)
        self.dom = etree.parse(template)# 從模板初始化
        self._slaves = {}  # 初始化從站字典
        self.AUTHORIZED_IPS = ["172.17.0.2", "127.0.0.1", "192.168.14.140", "172.18.0.1"]  # 定義授權 IP 清單

    def add_slave(self, slave_id):
        """
        Adds a slave with the given ID to the database.
        """
        if slave_id in self._slaves:
            raise DuplicatedKeyError(f"Slave with id {slave_id} already exists")
        
        # 初始化新的從站
        slave = MBSlave(slave_id, self.dom)  
        self._slaves[slave_id] = slave  # 儲存到內部管理結構
        logger.info(f"Added slave with ID {slave_id}")
        return slave

    def handle_request(self, query, request, mode, client_ip):
        """
        Handles a request. Return value is a tuple where element 0
        is the response object and element 1 is a dictionary
        of items to log.
        """
        request_pdu = None
        response_pdu = b""
        slave_id = None
        function_code = None
        func_code = None
        slave = None
        response = None

        try:
            # extract the pdu and the slave id
            slave_id, request_pdu = query.parse_request(request)
            if len(request_pdu) > 0:
                (func_code,) = struct.unpack(">B", request_pdu[:1])

            logger.debug("Working mode: %s" % mode)

            # 判斷是否為授權 IP
            if client_ip not in self.AUTHORIZED_IPS:
                logger.warning(f"!!!!!HACKER changed the train signal !!!!!(slave_db)")
            else:
                logger.info(f"!!!!!Authorized User changed the train signal !!!!!(slave_db)")

            if mode == "tcp":
                if slave_id == 0 or slave_id == 255:
                    slave = self.get_slave(slave_id)
                    # 傳遞 client_ip 參數
                    response_pdu = slave.handle_request(request_pdu, client_ip=client_ip)
                    response = query.build_response(response_pdu)
                else:
                    r = struct.pack(
                        ">BB", func_code + 0x80, defines.SLAVE_DEVICE_FAILURE
                    )
                    response = query.build_response(r)

            elif mode == "serial":
                if slave_id == 0:  # broadcasting
                    for key in self._slaves:
                        # 對廣播請求也傳遞 client_ip
                        response_pdu = self._slaves[key].handle_request(
                            request_pdu, client_ip=client_ip, broadcast=True
                        )
                    return (
                        None,
                        {
                            "request": request_pdu.hex(),
                            "slave_id": slave_id,
                            "function_code": func_code,
                            "response": "",
                        },
                    )
                elif 0 < slave_id <= 247:  # normal request handling
                    slave = self.get_slave(slave_id)
                    # 傳遞 client_ip 參數
                    response_pdu = slave.handle_request(request_pdu, client_ip=client_ip)
                    response = query.build_response(response_pdu)
                else:
                    r = struct.pack(
                        ">BB", func_code + 0x80, defines.SLAVE_DEVICE_FAILURE
                    )
                    response = query.build_response(r)

        except (MissingKeyError, IOError) as e:
            logger.error(e)
            r = struct.pack(">BB", func_code + 0x80, defines.SLAVE_DEVICE_FAILURE)
            response = query.build_response(r)
        except ModbusInvalidRequestError as e:
            logger.error(e)

        if slave:
            function_code = slave.function_code

        return (
            response,
            {
                "request": codecs.encode(request_pdu, "hex"),
                "slave_id": slave_id,
                "function_code": function_code,
                "response": codecs.encode(response_pdu, "hex"),
            },
        )


