"""
A module for a TelnetClient class that facilitates low-level interaction with a robot over Telnet protocol.

Constants:
    MAX_BYTES_TO_READ (int): Maximum bytes to read in each receive operation.
    RECV_TIMEOUT (int): Receive timeout value in seconds.
"""

import socket
from robot_exception import *

MAX_BYTES_TO_READ = 1024
RECV_TIMEOUT = 1


class TelnetClient:
    def __init__(self, ip: str, port: int):
        self._robot_ip = self._validate_ip(ip)  # The validated IP address of the robot.
        self._robot_port = self._validate_port(port)  # The validated port number of the robot.
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Socket object for the Telnet connection.

        if not self._connect():
            raise RobotConnException

    def _connect(self) -> bool:
        try:
            self._server.connect((self._robot_ip, self._robot_port))
            self.wait_recv(b'login:')
            self._server.sendall(b'as')
            self._server.sendall(b'\x0d\x0a')
            self.wait_recv(b'\x3e')
        except ConnectionError:
            return False
        return True

    def send_cmd(self, cmd: str):
        """ sends a command to the robot """
        self._server.sendall(cmd.encode() + b'\n')

    def wait_recv(self, *ends: b'') -> bytes:
        """ Waits to receive data from the robot until one of the specified end markers is encountered """
        incoming = b''
        while True:
            if not (recv := self._server.recv(MAX_BYTES_TO_READ)):
                break
            incoming += recv
            for eom in ends:
                if incoming.find(eom) > -1:     # Wait eom message from robot
                    return incoming

    def disconnect(self):
        """ Closes socket without checks """
        self._server.close()

    def handshake(self):
        """ Performs a handshake with the robot
             1 - without errors
            -1000 - connection errors and abort
        """
        self._server.sendall(b'\x0a')
        if not self.wait_recv(b"\x0d\x0a\x3e"):
            raise RobotConnException()

    @staticmethod
    def _validate_ip(ip) -> str:
        octets = ip.split(".")
        if len(octets) != 4:
            raise ValueError("ip-address must consist of 4 octets divided by dots")
        if not all(octet.isnumeric() and 0 <= int(octet) <= 255 for octet in octets):
            raise ValueError("ip-address must consist only of numeric characters with octets being in range [0, 255]")
        return ip

    @staticmethod
    def _validate_port(port) -> int:
        if 0 < port < 65535:
            return port
        raise ValueError(f"{port} is not a valid port number")


if __name__ == "__main__":
    robot = TelnetClient("127.0.0.1", 9105)
    robot.send_cmd("list")
    print(robot.wait_recv(b'\x0d\x0a\x3e').decode("UTF-8"))
    robot.disconnect()

