import struct
import logging

from modbus_tk.modbus import (
    Slave,
    ModbusError,
    ModbusInvalidRequestError,
    InvalidArgumentError,
    DuplicatedKeyError,
    InvalidModbusBlockError,
    OverlapModbusBlockError,
)
from modbus_tk import defines, utils
from conpot.helpers import str_to_bytes
from .modbus_block_databus_mediator import ModbusBlockDatabusMediator

logger = logging.getLogger(__name__)


class MBSlave(Slave):
    """
    Customized Modbus slave representation extending modbus_tk.modbus.Slave
    """

    def __init__(self, slave_id, dom):
        Slave.__init__(self, slave_id)
        self.dom = dom
        self.AUTHORIZED_IPS = ["172.17.0.2", "127.0.0.1", "192.168.14.140", "172.18.0.1"]  # 定義授權 IP 清單

    def handle_request(self, request_pdu, client_ip=None, broadcast=False):
        
        logger.debug(f"MBSlave handle_request called with client_ip: {client_ip}, broadcast: {broadcast}")
        """
        Parse the request PDU, verify client IP, and handle the Modbus request.
        """
        # 如果 client_ip 為 None，設置預設值或記錄錯誤
        if client_ip is None:
            logger.warning("Client IP is None. Using default value '127.0.0.1'.")
            client_ip = "127.0.0.1"

        # 驗證 client_ip 格式
        import ipaddress
        try:
            ipaddress.ip_address(client_ip)
        except ValueError:
            logger.error(f"Invalid client IP format: {client_ip}")
            return None

        # 檢查 IP 是否授權
        logger.debug(f"Handling request from client IP: {client_ip}")
        if client_ip.strip() not in [ip.strip() for ip in self.AUTHORIZED_IPS]:
            logger.warning(f"!!!!!HACKER changed the train signal from IP: {client_ip}!!!!!")
        else:
            logger.info(f"!!!!!Authorized User changed the train signal from IP: {client_ip}!!!!!")

        # Modbus 功能碼處理
        with self._data_lock:  # thread-safe
            try:
                (self.function_code,) = struct.unpack(">B", request_pdu[:1])
                
                if not self.function_code in self._fn_code_map:
                    raise ModbusError(defines.ILLEGAL_FUNCTION)

                response_pdu = self._fn_code_map[self.function_code](request_pdu)
                
                if response_pdu:
                    return struct.pack(">B", self.function_code) + response_pdu
                
                raise Exception(f"No response for function {self.function_code}")
            
            except ModbusError as e:
                logger.error(
                    f"Exception caught: {e}. (A proper response will be sent to the peer)"
                )
                return struct.pack(">BB", self.function_code + 128, e.get_exception_code())


