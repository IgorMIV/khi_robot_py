class ThreadState:
    """ Stores state of running pc or rcp thread on Kawasaki robot """
    name: str = ""
    running: bool = False
    step_num: int = -1
    completed_cycles: int = 0
    remaining_cycles: int = 0
