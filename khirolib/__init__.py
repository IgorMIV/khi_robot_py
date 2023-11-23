from src.irobot import *
import threading
from utils.time_limit import time_limit
from src.khilib_internal import KHITelnetLib
from queue import Queue


class Robot(IRobot, threading.Thread):
    def __init__(self, ip, telnet_port=23, connect_tcp=True, tcpip_port=22800):
        threading.Thread.__init__(self)
        super(Robot, self).__init__()
        self.daemon = True
        self._stopped = threading.Event()

        self._robot = KHITelnetLib(ip, telnet_port)

        self.subscription_vars = {}

        if connect_tcp:
            self._connect_tcp_ip()
        self.command_queue = Queue[Command]()

    def __enter__(self):
        self.start()
        return self

    def run(self) -> None:

        while not self._stopped.is_set():
            print("1")
            cmd = self.command_queue.get()

    def get_robot_state(self) -> dict:
        for rep in range(0, 5):
            with time_limit(5):
                if ret := self._robot.robot_state():
                    break
        return ret

    def status_pc(self) -> dict:
        return self._execute_cmd(Command(self._robot.status_pc()))

    def get_real(self, name: str) -> float:
        pass

    def get_pos(self, name: str) -> Position:
        pass

    def ereset(self) -> NoReturn:
        return 1

    def upload_program(self, filename: str = None, program_name: str = None, program_text: str = None, immediate=False):
        if filename is None:
            if (program_name is None) or (program_text is None):
                self._add_to_log("Error 1")
                print("You should set correct function arguments")
                return -2
        else:
            if (program_name is not None) or (program_text is not None):
                self._add_to_log("Error 2")
                print("You couldn't use loading from file and from string in the same time")
                return -2

        if filename is not None:
            f = open(filename, "r")
            first_line = f.readline()
            file_string = first_line + f.read()
            program_name = first_line.split(' ')[1].split('(')[0]
        else:
            file_string = '.PROGRAM ' + program_name + '\n'
            file_string += program_text + '\n'
            file_string += '.END' + '\n'

        cmd = Command(self._robot.upload_program(program_name, file_string))
        if immediate:
            self._execute_cmd(cmd)
        else:
            self.command_queue.put(cmd)  # TODO: return

    def delete_program(self, program_name: str):
        pass

    def execute_pc(self, program_name: str, thread: int):
        pass

    def abort_pc(self, *threads: int, program_name: str = ""):
        pass

    def kill_pc(self, *threads: int, program_name: str = ""):
        pass

    def execute_rcp(self, program_name: str, thread: int):
        pass

    def abort_rcp(self, *threads: int, program_name: str = ""):
        pass

    def kill_rcp(self, *threads: int, program_name: str = ""):
        pass

    def get_programs_list(self, immediate: bool = False) -> [str]:
        pass

    def lmove(self, point: Position, immediate: bool = False) -> NoReturn:
        pass

    def jmove(self, point: Position, immediate: bool = False) -> NoReturn:
        pass

    @staticmethod
    def _execute_cmd(cmd: Command):
        for attempt in range(0, cmd.maxtries):
            with time_limit(cmd.timeout):
                resp = cmd.cmd(cmd.args, cmd.kwargs)
                if resp:
                    break
        return resp

    def _connect_tcp_ip(self):
        threads = self.status_pc()
        print(threads)

    def _add_to_log(self, msg: str):
        pass  # TODO

    def stop(self):
        self._stopped.set()
        self._robot.disconnect()
        self.join()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


if __name__ == "__main__":
    with Robot("127.0.0.1", 9105, connect_tcp=False) as robot:
        print(robot.get_robot_state())
