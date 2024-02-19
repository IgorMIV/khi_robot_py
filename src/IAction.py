from abc import ABC, abstractmethod
from threading import Event
from khi_telnet_lib import *


ACTIVE_SCOPE = None


class IAction(ABC):
    def __init__(self, max_time: int = 10, max_retries: int = 3):
        self._max_time = max_time
        self._max_retries = max_retries
        self._result = None
        self._is_ready = Event()

        print("Enqued action into queue", ACTIVE_SCOPE)
        ACTIVE_SCOPE.enqueue(self)

    @abstractmethod
    def execute(self, telnet_client: TCPSockClient, tcpip_client: TCPSockClient):
        ...

    @abstractmethod
    def translate2as(self) -> str:
        ...
