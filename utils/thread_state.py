class ThreadState:
    """ Stores state of running pc or rcp thread on Kawasaki robot """
    thread_num: int = None
    name: str = ""
    running: bool = False
    step_num: int = -1
    completed_cycles: int = 0
    remaining_cycles: int = 0

    @property
    def is_exist(self):
        if self.name != "":
            return True
        else:
            return False

    @property
    def is_running(self):
        return self.running

    def __str__(self):
        ans = "Thread number: " + str(self.thread_num) + "\n" + \
              "Name: " + self.name + "\n" + \
              "Running: " + str(self.running) + "\n" + \
              "Step num: " + str(self.step_num) + "\n" + \
              "Completed cycles: " + str(self.completed_cycles) + "\n" + \
              "Remaining cycles: " + str(self.remaining_cycles) + "\n"
        return ans
