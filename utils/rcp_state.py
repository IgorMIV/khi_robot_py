class RCPState:
    """ Stores state of running pc or rcp thread on Kawasaki robot """
    name: str = ""
    motor_on: bool = True  # because if motor is ON - STATUS message isn't consist this state
    repeat_mode: bool = None
    monitor_speed: float = None
    program_speed: float = None
    accuracy: float = None
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

    @property
    def current_step_num(self):
        return int(self.step_num)

    @property
    def info(self):
        ans = "rcp: " + self.name + ", "
        ans += "run: " + str(self.running)
        return ans

    def __str__(self):
        ans = "RCP name: " + self.name + "\n" + \
              "Motor ON: " + str(self.motor_on) + "\n" + \
              "Repeat mode: " + str(self.repeat_mode) + "\n" + \
              "Monitor speed: " + str(self.monitor_speed) + "\n" + \
              "Program speed: " + str(self.program_speed) + "\n" + \
              "Accuracy: " + str(self.accuracy) + "\n" + \
              "Running: " + str(self.running) + "\n" + \
              "Step num: " + str(self.step_num) + "\n" + \
              "Completed cycles: " + str(self.completed_cycles) + "\n" + \
              "Remaining cycles: " + str(self.remaining_cycles) + "\n"
        return ans
