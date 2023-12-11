class RobotConnError(ConnectionError):
    def __init__(self):
        super().__init__("Can't establish connection with robot!")


class KawaSyntaxError:
    line: int
    text: str
    position: int
    code: str
    descr: str

    def __init__(self, descr: bytes):
        error_line, error_descr = descr.decode().split("\r\n")
        self.line = int((error_line_split := error_line.split())[0])
        self.text = " ".join(error_line_split[1:])
        self.code = error_descr[(code_pos := error_descr.find("^") + 2): code_pos + 5]
        self.descr = error_descr[code_pos + 6:]

    def __str__(self):
        return f"Error '{self.descr}' ({self.code}) at line {self.line} ({self.text})"


class RobotProgSyntaxError(Exception):
    errors: list[KawaSyntaxError]
    num_errors: int

    def __init__(self, errors_string: list[bytes]):
        self.errors = [KawaSyntaxError(error[1:-3]) for error in errors_string if error]
        self.num_errors = len(self.errors)
        error_text = "\n".join([str(error) for error in self.errors])
        super().__init__(f"File transmission not complete - {self.num_errors} errors found:\n" + error_text)


class RobotProgTransmissionError(Exception):
    def __init__(self, description: str):
        super().__init__(description)
