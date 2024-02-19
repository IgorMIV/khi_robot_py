from IAction import IAction
from khi_telnet_lib import *


class Move(IAction):
    def execute(self, telnet_client: TCPSockClient, tcpip_client: TCPSockClient):
        pass

    def translate2as(self) -> str:
        pass