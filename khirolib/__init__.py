import threading
import time
from src.action_queue import *
from utils.time_limit import time_limit
from src.robot_action import LMove, JMove
from libs.positionlib.positionlib import Position

TCPIP_COMM_PORT = 2000


class KHIRobot(ActionQueue, threading.Thread):
    """ Represents a KHI Robot.

    This class manages communication and execution of actions for a KHI robot.

    Args:
        ip (str): IP address of the robot.
        is_real_robot (bool, optional): Indicates whether the robot is real or simulated.
                                        TCP/IP communication doesn't work in KRoset simulation program.
                                        Defaults to False.
        online_mode (bool, optional): Indicates whether the robot is in online mode. Defaults to False.
    """
    def __init__(self, ip: str, is_real_robot: bool = False, online_mode: bool = False):
        super(KHIRobot, self).__init__()
        threading.Thread.__init__(self)

        self._ip = ip
        self._telnet_port = 23 if is_real_robot else 9105
        self._tcpip_port = TCPIP_COMM_PORT

        self._stopped = threading.Event()
        self._is_real_robot = is_real_robot
        self._online_mode = online_mode

        self._telnet_client: TCPSockClient | None = None
        self._tcpip_client: TCPSockClient | None = None

        self.connect()

    def connect(self):
        """ Connection sequence to the robot."""
        self._telnet_client = TCPSockClient(self._ip, self._telnet_port)
        telnet_connect(self._telnet_client)

        if self._is_real_robot:
            # Check for running tcp-ip process
            self._tcpip_client = TCPSockClient(self._ip, self._tcpip_port)

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
        """ Close sequence for robot.
        Used explicitly to close all connections or when __del__ is called
        """
        self._stopped.set()
        self.join()                          # Set flag to stop processing queue and wait for thread to join
        self._telnet_client.disconnect()
        if self._is_real_robot:
            self._tcpip_client.disconnect()  # Close all tcp connections
        super().close()


class KHIProgram(ActionQueue):
    pass


if __name__ == "__main__":
    queue_list = [ActionQueue(), ActionQueue(), ActionQueue()]

    for queue in queue_list:
        with queue:
            LMove(Position())
            LMove(Position())
            LMove(Position())

    exit(0)

    with KHIRobot("127.0.0.1") as robot1, KHIRobot("127.0.0.1") as robot2:

        LMove(Position())
        LMove(Position())
        LMove(Position())
        LMove(Position())


