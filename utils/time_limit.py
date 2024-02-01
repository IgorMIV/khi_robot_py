import signal
import threading
import sys
from contextlib import contextmanager
from typing import Callable, Any


@contextmanager
def time_limit(timeout: int, timeout_handler: Callable[[int, int], Any] = None, disable_for_debug: bool = True):
    """ Limits execution time to <timeout> seconds.
        If exceeded, by default raises TimeoutException,
        or executes timeout_handler(signum, frame) function
        Usage:
        with time_limit(timeout):
            do_something1
            do_something2
            ...
        By default, time limit will be off when in debug mode, because when pausing main thread,
        timer thread will still be going and raising exception. it can be disabled by "disable_for_debug" argument
    """
    disable_for_debug &= hasattr(sys, 'gettrace') and sys.gettrace() is not None  # Check for debug mode active
    if timeout_handler is None:
        def timeout_handler(_, __):
            raise TimeoutError(f"Execution timed out after {timeout} seconds")
    signal.signal(signal.SIGBREAK, timeout_handler)
    timer = threading.Timer(timeout, lambda: signal.raise_signal(signal.SIGBREAK) if not disable_for_debug else None)
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
