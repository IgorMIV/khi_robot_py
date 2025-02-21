import asyncio

class TCPSockClient:
    def __init__(self, ip: str, port: int):
        """ Initialize AsyncTCPSockClient instance.

        Args:
            ip (str): IP address of the robot.
            port (int): Port number of the robot.
        """
        self._ip = ip
        self._port = port
        self._reader = None
        self._writer = None

    async def connect(self):
        """ Establish connection to the robot. """
        try:
            self._reader, self._writer = await asyncio.open_connection(self._ip, self._port)
        except Exception as e:
            print(f"Failed to connect: {e}")
            self._reader = None
            self._writer = None

    def set_timeout(self, timeout: int) -> None:
        """ Set timeout for the connection (not applicable in asyncio). """
        pass  # Timeout handling is different in asyncio

    async def send_msg(self, msg: str, end: bytes = b'\n') -> None:
        """ Send a message to the robot.

        Args:
            msg (str): Message to be sent.
            end (bytes, optional): End marker for the message. Defaults to b'\n'.
        """
        if self._writer is None:
            raise ConnectionError("Connection not established.")
        self._writer.write(msg.encode() + end)
        await self._writer.drain()  # Ensure the message is sent

    async def wait_recv(self, *ends: bytes) -> bytes:
        """ Wait to receive data from the robot until one of the specified end markers is encountered.

        Args:
            *ends (bytes): End markers to wait for.

        Returns:
            bytes: Received data.

        Raises:
            TimeoutError: If receive operation times out.
        """
        if self._reader is None:
            raise ConnectionError("Connection not established.")

        incoming = b""
        try:
            while True:
                data = await self._reader.read(1)  # Read one byte
                if not data:
                    break  # Connection closed
                incoming += data
                for eom in ends:
                    if incoming.endswith(eom):  # Check for end markers
                        return incoming
        except asyncio.TimeoutError:
            raise TimeoutError("Receive operation timed out")

    def disconnect(self) -> None:
        """ Closes connection. """
        if self._writer:
            self._writer.close()
            asyncio.run(self._writer.wait_closed())
