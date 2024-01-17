"""
A module for a TCPSocketClient class that facilitates low-level interaction with a robot over tcp/ip protocol.

Constants:
    RECV_TIMEOUT (int): Receive timeout value in seconds.
    SERVER_TIMEOUT (int): Time limit for connecting to robot
"""

import socket

RECV_TIMEOUT = 1
SERVER_TIMEOUT = 10


class TCPSocketClient:
    def __init__(self, ip: str, port: int):
        self._robot_ip = ip                                               # IP address of the robot.
        self._robot_port = port                                           # port number of the robot.

        self._client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Socket object for the Telnet connection.
        self._client.settimeout(SERVER_TIMEOUT)                           # Set time limit for connecting to robot
        self._client.connect((self._robot_ip, self._robot_port))

    def send_msg(self, cmd: str, end: bytes = b'\n') -> None:
        self._client.sendall(cmd.encode() + end)

    def send_bytes(self, cmd: bytes) -> None:
        self._client.sendall(cmd)

    def wait_recv(self, *ends: b'') -> bytes:
        """ Waits to receive data from the robot until one of the specified end markers is encountered """
        incoming = b""
        try:
            while True:
                incoming += self._client.recv(1)  # Receive symbols one-by-one from socket
                for eom in ends:
                    if incoming.find(eom) > -1:  # Wait eom message from robot
                        return incoming
        except socket.timeout:
            raise TimeoutError

    def disconnect(self) -> None:
        self._client.close()
