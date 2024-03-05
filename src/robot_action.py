from src.action_queue import IAction
from src.khi_telnet_lib import *
from libs.positionlib.positionlib import Position


""" Implements basic actions for Kawasaki robots using IAction interface """


class LMove(IAction):
    """ Offline command to move to point with linear interpolation """
    _is_blocking = False

    def __init__(self, point: Position, **kwargs):
        super().__init__(**kwargs)
        self._point = point

    def is_async(self) -> bool:
        return True

    def execute(self, telnet_client: TCPSockClient):
        pass

    def translate2as(self) -> str:
        return f"LMOVE TRANS{self._point.get_kawasaki()}"


class JMove(IAction):
    """ Offline command to move to point with joint interpolation """
    _is_blocking = False

    def __init__(self, point: Position, **kwargs):
        super().__init__(**kwargs)
        self._point = point

    def is_async(self) -> bool:
        return True

    def execute(self, telnet_client: TCPSockClient):
        pass

    def translate2as(self) -> str:
        return f"JMOVE TRANS{self._point.get_kawasaki()}"
