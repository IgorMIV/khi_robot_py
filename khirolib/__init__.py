import threading
import time
from src.action_queue import *
from src.khi_telnet_lib import telnet_connect
from utils.time_limit import time_limit
from src.robot_action import LMove, JMove
from libs.positionlib.positionlib import Position


TCPIP_COMM_PORT = 2000
TELNET_DEF_PORT = 23
TELNET_SIM_PORT = 9105


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
        self._telnet_port = TELNET_DEF_PORT if is_real_robot else TELNET_SIM_PORT
        self._tcpip_port = TCPIP_COMM_PORT

        self._stopped = threading.Event()
        self._is_real_robot: bool = is_real_robot
        self._online_mode: bool = online_mode

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
    def __init__(self, name: str):
        self.name = name
        super(KHIProgram, self).__init__()

    def translate_to_as(self) -> str:
        commands = [f".PROGRAM {self.name}()"]
        for action in self.action_queue:
            commands.append(action.translate2as())
        commands.append(".END")
        return "\n".join(commands)

    def close(self):
        pass


if __name__ == "__main__":
    pg_list = [KHIProgram(str(name)) for name in range(5)]

    for pg in pg_list:
        with pg:
            LMove(Position())
            LMove(Position())
            LMove(Position())
        print(pg.translate_to_as())

    with KHIProgram("test1") as robot1, KHIProgram("test2") as robot2:

        LMove[robot1](Position())
        LMove[robot1](Position())
        LMove[robot1](Position())

        LMove[robot2](Position())
        LMove[robot2](Position())
        LMove[robot2](Position())

        print(robot1.translate_to_as())
        print(robot2.translate_to_as())



    # with KHIRobot("127.0.0.1") as robot1, KHIRobot("127.0.0.1") as robot2:
    #
    #     LMove(Position())
    #     LMove(Position())
    #     LMove(Position())
    #     LMove(Position())
