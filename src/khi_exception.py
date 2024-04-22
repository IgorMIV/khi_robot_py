"""
A module containing custom exception classes for handling Kawasaki robot controller errors and communication issues.
"""


class KHISyntaxError:
    """ Represents a syntax error encountered during Kawa program execution.

    Attributes:
        line (int): Line number where the error occurred.
        text (str): Text describing the error.
        position (int): Position where the error occurred.
        code (str): Code associated with the error.
        descr (str): Description of the error.
    """

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


class KHIConnError(ConnectionError):
    def __init__(self):
        super().__init__("Can't establish connection with robot!")


class KHIProgSyntaxError(Exception):
    """ Raised when loading AS program with syntax errors """
    errors: list[KHISyntaxError]
    num_errors: int

    def __init__(self, errors_string: list[bytes]):
        self.errors = [KHISyntaxError(error[1:-3]) for error in errors_string[:-1]]
        self.num_errors = len(self.errors)
        error_text = "\n".join([str(error) for error in self.errors])
        super().__init__(f"File transmission not complete - {self.num_errors} errors found:\n" + error_text)


class KHIProgNotExistError(ValueError):
    """ Raised when trying to execute AS program that doesn't exist """
    def __init__(self, program_name: str):
        super().__init__(f"Program {program_name} does not exist")


class KHIProgRunningError(ValueError):
    """ Raised when trying to upload / delete / execute program that is already running in another thread """
    def __init__(self, program_name: str):
        super().__init__(f"Program {program_name} is already running in another thread")


class KHIProgLoadedError(ValueError):
    """ Raised when trying to upload / delete / execute program that is halted, but not killed in another thread """
    def __init__(self, program_name: str):
        super().__init__(f"Program {program_name} is halted via abort, but still loaded")


class KHIProgActiveError(ValueError):
    """ Raised when trying to kill running program.
    Use PCABORT or PCEND to halt it immediately or wait for completion accordingly """
    def __init__(self, thread_num: int):
        super().__init__(f"Program is running in thread {thread_num}")


class KHIThreadBusyError(ValueError):
    """ Raised when trying to execute PC program in busy thread """
    def __init__(self, thread_num: int):
        super().__init__(f"Another program is running in thread {thread_num}")


class KHIProgTransmissionError(Exception):
    def __init__(self, description: str):
        super().__init__(description)


class KHITeachModeError(Exception):
    """ Raised when executing motion command with teach mode set on the controller """
    def __init__(self):
        super().__init__("Cannot execute motion instructions in TEACH mode")


class KHITeachLockError(Exception):
    """ Raised when executing motion command with teach pendant with lock ON """
    def __init__(self):
        super().__init__("Cannot execute motion instructions when teach pendant lock is ON")


class KHIMotorsOffError(Exception):
    """ Raised when executing motion command with motors powered OFF """
    def __init__(self):
        super().__init__("Cannot execute motion instructions with motors powered off")
