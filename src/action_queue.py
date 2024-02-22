from __future__ import annotations
from abc import ABC, abstractmethod
from src.khi_telnet_lib import *
from collections import deque
from typing import Optional


class ActionQueue:
    instance_stack = deque()

    def __init__(self):
        self.queue = deque()

    def __new__(cls, *args, **kwargs):
        if cls not in cls.instance_stack:
            cls.instance_stack.append(super().__new__(cls))
        return cls.instance_stack[-1]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ Safely stop data transmission and close socket """
        self.close()

    def close(self):
        if not (self.instance_stack[-1] is self):
            raise Exception("You're trying to exit ActionQueue scope that isn't active")
        self.instance_stack.pop()


class IAction(ABC):
    _is_blocking: bool

    def __init__(self, max_time: int = 10, max_retries: int = 3):
        self.max_time = max_time
        self.max_retries = max_retries
        if self._is_blocking is None:
            raise Exception("is_blocking field must be defined in derived class")

    def __new__(cls, *args, max_time: int = 10, max_retries: int = 3):
        instance = super().__new__(cls)

        instance.__init__(*args, max_time=max_time, max_retries=max_retries)
        target = ActionQueue.instance_stack[-1]

        if cls._is_blocking and hasattr(target, "execute_action"):
            # If running on robot and action needs to be called immediately
            res = target.execute_action(cls)
            return res

        target.queue.append(instance)

    @abstractmethod
    def execute(self, telnet_client: TCPSockClient):
        ...

    @abstractmethod
    def translate2as(self) -> str:
        ...