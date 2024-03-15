from __future__ import annotations
from abc import ABC, abstractmethod
from src.khi_telnet_lib import TCPSockClient
from collections import deque
from typing import Callable, Optional


class ActionQueue(ABC):
    instance_stack: deque[ActionQueue] = deque()

    def __init__(self):
        self.action_queue: deque[IAction] = deque()

    def __new__(cls, *args, **kwargs) -> ActionQueue:
        """ On creation of object push itself to instance stack """
        cls.instance_stack.append(super().__new__(cls))
        return cls.instance_stack[-1]

    def enter_context(self) -> None:
        if self.instance_stack[-1] is not self:
            self.instance_stack.append(self)

    def exit_context(self) -> None:
        if not (self.instance_stack[-1] is self):
            raise Exception("You're trying to exit ActionQueue context that isn't active")
        self.instance_stack.pop()

    def __enter__(self):
        if self in self.instance_stack:
            self.enter_context()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit_context()

    def __del__(self):
        """ Runs close() abstract method implementation on deletion of an object """
        self.close()

    @abstractmethod
    def close(self):
        """ Method to gracefully close all connections before cleanup if needed """
        pass


class IAction(ABC):
    _explicit_target: ActionQueue | None = None
    result = None

    def __init__(self, max_time: int = 10, max_retries: int = 3, result_callback: Optional[Callable] = None):
        self.max_time = max_time
        self.max_retries = max_retries
        self._result_callback = result_callback

        target = self._explicit_target or ActionQueue.instance_stack[-1]
        if not self.is_async and hasattr(target, "execute_action"):
            target.execute_action(self)
        else:
            target.action_queue.append(self)   # If action is async or target can't execute actions

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)  # Construct object normally
        if instance.is_async:            # If is async (no data needs to be returned immediately), init normally
            return instance
        instance.__init__(*args, **kwargs)
        return instance.result

    def __class_getitem__(cls, item: ActionQueue):
        class IntermediateAction(cls, ABC):
            pass
        IntermediateAction._explicit_target = item
        return IntermediateAction

    @property
    @abstractmethod
    def is_async(self) -> bool:
        pass

    @abstractmethod
    def execute(self, telnet_client: TCPSockClient):
        pass

    @abstractmethod
    def translate2as(self) -> str:
        pass


if __name__ == "__main__":
    class TestQueue(ActionQueue):
        def close(self):
            pass

    class TestAction(IAction):
        def __init__(self, name, **kwargs):
            self.name = name
            super().__init__(**kwargs)

        def is_async(self) -> bool:
            return True

        def execute(self, telnet_client: TCPSockClient):
            pass

        def translate2as(self) -> str:
            pass

    with TestQueue() as q, TestQueue() as q2:
        TestAction(1)
        TestAction(2)
        TestAction(3)

        with TestQueue() as q1:
            TestAction(1)
            TestAction(2)
            TestAction(3)

        TestAction(1)
        TestAction(2)
        TestAction(3)