
class ThreadState:
    name: str  # Name of running program or "No" if no program is running
    running: bool
    completed_cycles: int
    remaining_cycles: int
