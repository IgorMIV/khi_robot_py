import khi_tcpip_lib
import khi_telnet_lib
from queue import Queue


class KHIRobot:
    def __init__(self, ip: str, port: int):
        self._ip = ip
        self._port = port
        self._command_queue = Queue

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ Safely stop data transmission and close socket """
        pass
    

if __name__ == "__main__":
    with KHIRobot("123", 123) as robot:
        raise Exception("test")
