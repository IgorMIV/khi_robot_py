import queue
import IAction
from RobotAction import Move


class ActionQueue:
    def __init__(self):
        global ACTIVE_SCOPE
        self._queue = queue.Queue()
        self._prev_queue = IAction.ACTIVE_SCOPE
        IAction.ACTIVE_SCOPE = self

    def __enter__(self):
        return self

    def enqueue(self, action: IAction):
        self._queue.put(action)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ Safely stop data transmission and close socket """
        self.close()

    def close(self):
        if not (IAction.ACTIVE_SCOPE is self):
            raise Exception("You're trying to exit ActionQueue scope that isn't active")
        IAction.ACTIVE_SCOPE = self._prev_queue


if __name__ == "__main__":
    with ActionQueue() as queue1:

        print(IAction.ACTIVE_SCOPE)
        Move()

        with ActionQueue() as queue2:

            print(IAction.ACTIVE_SCOPE)
            Move()

        print(IAction.ACTIVE_SCOPE)
        Move()

