"""
A module for a TelnetClient class that facilitates low-level interaction with a robot over Telnet protocol.

Constants:
    MAX_BYTES_TO_READ (int): Maximum bytes to read in each receive operation.
    RECV_TIMEOUT (int): Receive timeout value in seconds.
    SERVER_TIMEOUT (int): Time limit for connecting to robot
"""

import socket

MAX_BYTES_TO_READ = 1024
RECV_TIMEOUT = 1
SERVER_TIMEOUT = 10


class TelnetClient:
    def __init__(self, ip: str, port: int):
        self._robot_ip = self._validate_ip(ip)                            # The validated IP address of the robot.
        self._robot_port = self._validate_port(port)                      # The validated port number of the robot.

        self._client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Socket object for the Telnet connection.
        self._client.settimeout(SERVER_TIMEOUT)                           # Set time limit for connecting to robot
        self._client.connect((self._robot_ip, self._robot_port))

    def send_msg(self, cmd: str, end: bytes = b'\n'):
        """ sends a command to the robot """
        self._client.sendall(cmd.encode() + end)

    def send_bytes(self, cmd: bytes):
        self._client.sendall(cmd)

    def wait_recv(self, *ends: b'') -> bytes:
        """ Waits to receive data from the robot until one of the specified end markers is encountered """
        incoming = b''
        while True:
            if not (recv := self._client.recv(MAX_BYTES_TO_READ)):
                break
            incoming += recv
            for eom in ends:
                if incoming.find(eom) > -1:  # Wait eom message from robot
                    return incoming

    def disconnect(self):
        """ Closes socket without checks """
        self._client.close()

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
    robot.send_msg("list")
    print(robot.wait_recv(b'\x0d\x0a\x3e').decode("UTF-8"))
    robot.disconnect()
