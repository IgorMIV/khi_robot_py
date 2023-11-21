from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Callable, Any, NoReturn
from libs.positionlib.positionlib import Position


@dataclass
class Command:
    cmd: Callable
    args: tuple = ()
    kwargs: tuple = ()
    maxtries: int = 5
    timeout: int = 3


@dataclass
class Answer:
    data: Any
    progress: float


class IRobot(ABC):
    """ Abstract class defining the interface for a robot controller library.
     This class defines the methods that need to be implemented to control the robot """

    @abstractmethod
    def get_robot_state(self) -> dict:
        """ Retrieve the current state of the robot.
        State information consists of main robot signals, such as:
         - motor_power
         - cycle_start
         - rgso
         - error
         - repeat
         - run
        return example:
        {'motor_power': "b'OFF'", 'cycle_start': "b'OFF'", 'rgso': b'OFF', 'error': '-', 'repeat': b'ON', 'run': b'ON'}
        """
        pass

    @abstractmethod
    def status_pc(self) -> dict:
        pass

    @abstractmethod
    def get_real(self, name: str) -> float:
        pass

    @abstractmethod
    def get_pos(self, name: str) -> Position:
        pass

    @abstractmethod
    def ereset(self) -> NoReturn:
        pass

    @abstractmethod
    def upload_program(self, filename: str = None, program_name: str = None, program_text: str = None, immediate=False):
        pass

    @abstractmethod
    def delete_program(self, program_name: str):
        pass

    @abstractmethod
    def execute_pc(self, program_name: str, thread: int):
        pass

    @abstractmethod
    def abort_pc(self, *threads: int, program_name: str = ""):
        pass

    @abstractmethod
    def kill_pc(self, *threads: int, program_name: str = ""):
        pass

    @abstractmethod
    def execute_rcp(self, program_name: str, thread: int):
        pass

    @abstractmethod
    def abort_rcp(self, *threads: int, program_name: str = ""):
        pass

    @abstractmethod
    def kill_rcp(self, *threads: int, program_name: str = ""):
        pass

    @abstractmethod
    def get_programs_list(self, immediate: bool = False) -> [str]:
        pass

    @abstractmethod
    def lmove(self, point: Position, immediate: bool = False) -> NoReturn:
        pass

    @abstractmethod
    def jmove(self, point: Position, immediate: bool = False) -> NoReturn:
        pass