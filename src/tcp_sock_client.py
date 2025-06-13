"""
A module for a TCPSocketClient class that facilitates low-level interaction with a robot over tcp/ip protocol.

Constants:
    RECV_TIMEOUT (int): Receive timeout value in seconds.
    SERVER_TIMEOUT (int): Time limit for connecting to robot
"""

import socket
import select

RECV_TIMEOUT = 1
SERVER_TIMEOUT = 1


class TCPSockClient:
    def __init__(self, ip: str, port: int, timeout: int | None = None):
        """
        Initialize TCPSockClient instance.

        Args:
            ip (str): IP address of the robot.
            port (int): Port number of the robot.
            timeout (int | None, optional): Connection timeout value in seconds. Defaults to None.
        """
        self._ip: str = ip                                               # IP address of the robot.
        self._port: int = port                                           # port number of the robot.

        self._client: socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._client.settimeout(SERVER_TIMEOUT if timeout is None else timeout)
        # self._client.connect((self._ip, self._port))

        self._client.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        try:
            self._client.connect((self._ip, self._port))
            self.connected = True
        except (socket.timeout, socket.error):
            self.connected = False

    def set_timeout(self, timeout) -> None:
        self._client.settimeout(timeout)

    def reset_timeout(self) -> None:
        self._client.settimeout(SERVER_TIMEOUT)

    def send_msg(self, msg: str, end: bytes = b'\n') -> None:
        """ Send a message to the robot.
        Args:
            msg (str): Message to be sent.
            end (bytes, optional): End marker for the message. Defaults to b'\n'.
        """
        # print("sent:", msg)
        self._client.sendall(msg.encode() + end)

    def send_bytes(self, msg: bytes) -> None:
        """ Send bytes to the robot.
        Args:
            msg (bytes): Bytes to be sent.
        """
        # print("sent:", msg)
        self._client.sendall(msg)

    def is_data_available(self) -> bool:
        """Check if data is available to read from the socket."""
        ready_to_read, _, _ = select.select([self._client], [], [], 0.1)
        return bool(ready_to_read)

    def wait_recv(self, *ends: bytes) -> bytes:
        """ Wait to receive data from the robot until one of the specified end markers is encountered.
        Args:
            *ends (bytes): End markers to wait for.

        Returns:
            bytes: Received data.

        Raises:
            TimeoutError: If receive operation times out.
        """
        incoming = b""
        try:
            while True:
                incoming += self._client.recv(1)  # Receive symbols one-by-one from socket
                # print("INC", incoming)
                for eom in ends:
                    if incoming.find(eom) > -1:  # Wait eom message from robot
                        # print("received:", incoming)
                        return incoming
        except socket.timeout:  # Off timeout while waiting program complete message
            raise TimeoutError

    def flush_input_buffer(self) -> None:
        """ Clear any data currently in the input buffer without blocking. """
        self._client.setblocking(False)
        try:
            while True:
                if not self.is_data_available():
                    break
                try:
                    self._client.recv(1024)
                except BlockingIOError:
                    break
        finally:
            self._client.setblocking(True)

    def is_connected(self) -> bool:
        """ Check connection """
        try:
            read, _, error = select.select([self._client], [], [self._client], 0)
            if error:
                self.connected = False
                return False

            self._client.send(b"")
            return True
        except (socket.error, BrokenPipeError, OSError):
            self.connected = False
            return False

    def disconnect(self) -> None:
        """ Closes connection """
        self._client.close()
