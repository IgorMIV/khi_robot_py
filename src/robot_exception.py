
class RobotConnError(ConnectionError):
    def __init__(self):
        super().__init__("Can't establish connection with robot!")


class RobotProgSyntaxError(Exception):
    errors: list
    num_errors: int

    def __init__(self, errors: list):
        self.errors = errors
        self.num_errors = len(errors)
        super().__init__(f"File transmission not complete - Errors found\nErrors list:\n{self.errors}\n"
                         f"Num errors: {self.num_errors}")


class RobotProgTransmissionError(Exception):
    def __init__(self, description: str):
        super().__init__(description)
