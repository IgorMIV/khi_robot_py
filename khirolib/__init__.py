import threading
import time
from src.action_queue import *
from utils.time_limit import time_limit
from src.robot_action import LMove, JMove
from libs.positionlib.positionlib import Position

TCPIP_COMM_PORT = 2000


class KHIRobot(ActionQueue, threading.Thread):
    def __init__(self, ip: str, is_real_robot: bool = False, online_mode: bool = False):
        super(KHIRobot, self).__init__()
        threading.Thread.__init__(self)

        self._stopped = threading.Event()
        self._is_real_robot = is_real_robot
        self._online_mode = online_mode

        self._telnet_client = TCPSockClient(ip, 23 if is_real_robot else 9105)
        telnet_connect(self._telnet_client)

        # Check for running tcp-ip program

        if is_real_robot:
            self._tcpip_client = TCPSockClient(ip, TCPIP_COMM_PORT)

        self.start()

    def is_real_robot(self):
        return self._is_real_robot

    def run(self):
        while not self._stopped.is_set():
            time.sleep(1)

    def execute_action(self, action: IAction):
        for attempt in range(action.max_retries):
            with time_limit(action.max_time):
                action.execute(self._telnet_client)

    def close(self):
        self._stopped.set()
        self.join()                          # Set flag to stop processing queue and wait for thread to join
        self._telnet_client.disconnect()
        if self._is_real_robot:
            self._tcpip_client.disconnect()  # Close all tcp connections
        super().close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == "__main__":
    with KHIRobot("127.0.0.1") as robot1, KHIRobot("127.0.0.1") as robot2:

        LMove(Position(), robot2)
        LMove(Position())
        LMove(Position(), robot2)
        LMove(Position(), robot2)


