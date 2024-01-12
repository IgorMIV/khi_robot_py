import math
from utils.thread_state import ThreadState
from telnet_client import TelnetClient
from robot_exception import *


# One package size in bytes for splitting large programs. Slightly faster at higher values
# It's 2962 bytes in KIDE and robot is responding for up to 3064 bytes
UPLOAD_BATCH_SIZE = 1000


NEWLINE_MSG = b"\x0d\x0a\x3e"                      # "\r\n>" - Message when clearing terminal
START_LOADING = b"LOAD using.rcc\n" + bytes.fromhex('02 41 20 20 20 20 30 17')
CANCEL_LOADING = bytes.fromhex('02 43 20 20 20 20 30 1a 17 02 45 20 20 20 20 30 17')
PKG_RECV = b"\x05\x02\x43\x17"                     # Byte sequence when program batch is accepted
SYNTAX_ERROR = "\r\nSTEP syntax error.\r\n(0:Change to comment and continue, 1:Delete program and abort)\r\n".encode()
CONFIRM_TRANSMISSION = b"\x73\x29\x0d\x0a\x3e"     # end of "N errors)"
SAVE_LOAD_ERROR = b"\x65\x73\x73\x2e\x0d\x0a\x3e"  # Byte sequence when previous save/load operation was interrupted
HARD_ABORT = b"\x05\x02\x45\x17"                   #
CONFIRMATION_REQUEST = b'\x30\x29\x20'             # Are you sure ? (Yes:1, No:0)?
PROGRAM_COMPLETED = b"Program completed.No = 1"


ALREADY_IN_USE = b"program already in use."                 # Program is already running in different thread
PROG_IS_LOADED = b"KILL or PCKILL to delete program."       # Program is halted via pcabort. Use KILL pr PCKILL
THREAD_IS_BUSY = b"PC program is running."                  # Another program is running in this thread
PROG_NOT_EXIST = b"Program does not exist."                 # Program does not exist error
PROG_IS_ACTIVE = b"Cannot KILL program that is running."    # Program is active and can't be killed
TEACH_MODE_ON = b"program in TEACH mode."                   # Running RCP program in teach mode
TEACH_LOCK_ON = b"teach lock is ON."                        # Running RCP program when pendant teach lock is on
MOTORS_DISABLED = b"motor power is OFF."                    # Running RCP program with motors powered OFF


class KHITelnetLib:
    def __init__(self, ip: str, port: int):
        self._ip_address = ip
        self._port_number = port
        self._client = TelnetClient(ip, port)
        self._connect()

    def _connect(self) -> None:
        try:
            self._client.wait_recv(b"login")              # Send 'as' as login for kawasaki telnet terminal
            self._client.send_msg("as")                   # Confirm with carriage return and line feed control symbols
            self._client.wait_recv(NEWLINE_MSG)           # wait for '>' symbol of a kawasaki terminal new line
        except (TimeoutError, ConnectionRefusedError):
            raise KawaConnError()

    def handshake(self) -> None:
        """ Performs a handshake with the robot and raises an exception if something fails """
        self._client.send_msg("")                         # Send empty command
        if not self._client.wait_recv(NEWLINE_MSG):       # Wait for newline symbol
            raise KawaConnError()

    def ereset(self) -> None:
        self._client.send_msg("ERESET")
        self._client.wait_recv(NEWLINE_MSG)

    def close_connection(self) -> None:
        self._client.disconnect()

    def get_system_switch_state(self, switch_name: str) -> bool:
        """ Sets robot system switch state """
        self._client.send_msg("SWITCH " + switch_name)
        return self._client.wait_recv(NEWLINE_MSG).split()[-2].decode() == "ON"

    def set_system_switch_state(self, switch_name: str, value: bool) -> None:
        """ Sets robot system switch. Note that switch might be read-only,
            in that case switch value won't be changed """
        self._client.send_msg(switch_name + "ON" if value else "OFF")
        self._client.wait_recv(NEWLINE_MSG)

    def get_error_descr(self) -> str:
        """ Returns robot error state description, empty string if no error """
        self._client.send_msg("type $ERROR(ERROR)")
        res = self._client.wait_recv(NEWLINE_MSG).decode()
        if "Value is out of range." not in res:
            return ' '.join(res.split('\r\n')[1:-1])
        return ""

    @staticmethod
    def _parse_program_thread(robot_msg: str) -> ThreadState:
        if "Program is not running" not in robot_msg:
            res = ThreadState()
            lines = robot_msg.split("\r\n")[1:-1]
            res.running = True
            res.name = lines[-1].split()[0]
            res.step_num = lines[-1].split()[2]
            for line in lines:
                if "Completed cycles: " in line:
                    res.completed_cycles = int(line.split()[-1])
                elif "Remaining cycles: " in line:
                    res.remaining_cycles = -1 if "Infinite" in line else int(line.split()[-1])
                    break  # Because remaining cycles number always last
            return res
        return ThreadState()

    def get_pc_status(self, threads: int) -> [ThreadState]:
        """ Checks the status of a list of PC programs based on a packed integer representing threads to check.

        Args:
            threads (int): An integer representing the threads to be checked for status. The first five bits
                correspond to the threads: bit 0 represents thread 1, bit 1 represents thread 2, and so on.
                A set bit (1) means the corresponding thread's status will be checked.

        Returns:
            list[ThreadState]: A list containing data objects, each representing the status of a thread.

        Note:
            This method is considered to be low-level and is called from another class where
            input validation and packing is done, but for testing it can be called directly
            with help of utility function "pack_threads(*args)" provided in this module
        """
        pc_thread_states = [ThreadState() for _ in range(5)]
        for thread_num in range(5):
            if threads & (1 << thread_num):  # Unpack threads from 5-bit integer representation
                self._client.send_msg(f"PCSTATUS {thread_num + 1}:")
                response = self._client.wait_recv(NEWLINE_MSG).decode()
                pc_thread_states[thread_num] = self._parse_program_thread(response)
        return pc_thread_states

    def get_rcp_status(self) -> ThreadState:
        """ Checks the status of current active RCP program.
        Returns:
            ThreadState: data object, representing the status of an active RCP program."""
        self._client.send_msg("STATUS")
        return self._parse_program_thread(self._client.wait_recv(NEWLINE_MSG).decode())

    def upload_program(self, program_string: str, proceed_on_error: bool = True) -> None:
        """ Uploads a program to the robot.

        Args:
            program_string (str): Text of the program to upload.
            proceed_on_error (bool, optional): Flag to continue uploading on encountering errors.
                                               When True, lines with errors will be commented

        Raises:
            RobotProgTransmissionError: If there is an error during transmission.
            RobotProgSyntaxError: If there are syntax errors in the uploaded program.

        Returns:
            None

            TODO: Split method into multiple simplified
        """
        program_bytes = bytes(program_string, "utf-8")
        num_packages = math.ceil(len(program_bytes) / UPLOAD_BATCH_SIZE)
        file_packages = [
            (b"\x02\x43\x20\x20\x20\x20\x30"
             + program_bytes[idx * UPLOAD_BATCH_SIZE: (idx + 1) * UPLOAD_BATCH_SIZE] + b"\x17")
            for idx in range(num_packages)
        ]

        self._client.send_bytes(START_LOADING)
        res = self._client.wait_recv(b'Loading...(using.rcc)\r\n', SAVE_LOAD_ERROR)
        if SAVE_LOAD_ERROR in res:
            raise KawaProgTransmissionError("SAVE/LOAD in progress")

        errors_string = b""
        for byte_package in file_packages:
            self._client.send_bytes(byte_package)
            response = self._client.wait_recv(SYNTAX_ERROR, HARD_ABORT, PKG_RECV)

            while proceed_on_error and SYNTAX_ERROR in response:
                # Filter "Program ___()\r\n " uploading program confirmation occurring in random places
                response = response[response.find(b"()\r\n ") + 5:] if (response.startswith(b"Program") and
                                                                        b"()\r\n " in response) else response
                errors_string += response
                self._client.send_msg("0")
                self._client.wait_recv(b"0\r\n")
                response = self._client.wait_recv(PKG_RECV, SYNTAX_ERROR)
            if not proceed_on_error and SYNTAX_ERROR in response:  # On error delete program and abort transmission
                errors_string += response
                self._client.send_msg("1")
                self._client.wait_recv(b"1\r\n")
                break

            if HARD_ABORT in response:  # Maybe unused
                raise KawaProgAlreadyRunning("")

        self._client.send_bytes(CANCEL_LOADING)
        self._client.wait_recv(CONFIRM_TRANSMISSION)

        if errors_string:
            raise KawaProgSyntaxError(errors_string.split(SYNTAX_ERROR))

    def delete_program(self, program_name: str) -> None:
        self._client.send_msg("DELETE/P/D " + program_name)
        self._client.wait_recv(CONFIRMATION_REQUEST)
        self._client.send_msg("1")
        res = self._client.wait_recv(b"1" + NEWLINE_MSG)
        if ALREADY_IN_USE in res:
            raise KawaProgAlreadyRunning(program_name)
        elif PROG_IS_LOADED in res:
            raise KawaProgStillLoaded(program_name)

    def pc_execute(self, program_name: str, thread_num: int) -> None:
        """ Executes PC program on selected thread
        Args:
             program_name (str): Name of a PC program inside robot's memory to be executed
             thread_num (int): PC program thread
        Note:
             When trying to execute pc program which has motion commands in it (LMOVE, JMOVE),
             robot won't generate error until the instruction is reached.
        """
        self._client.send_msg(f"PCEXE {str(thread_num)}: {program_name}")
        res = self._client.wait_recv(NEWLINE_MSG)

        if PROG_NOT_EXIST in res:
            raise KawaProgNotExistError(program_name)
        elif ALREADY_IN_USE in res:
            raise KawaProgAlreadyRunning(program_name)
        elif THREAD_IS_BUSY in res:
            raise KawaThreadBusy(thread_num)

    def pc_abort(self, threads: int) -> None:
        """ Aborts running PC programs on selected threads.
        Args: threads (int): An integer representing the threads to be checked for status.
                             See "status_pc" for more info
        """
        for thread_num in range(5):
            if threads & (1 << thread_num):
                self._client.send_msg(f"PCABORT {thread_num + 1}:")
                self._client.wait_recv(NEWLINE_MSG)

    def pc_end(self, threads: int) -> None:
        """ Softly ends selected program(s) waiting for the current cycle to be completed """
        for thread_num in range(5):
            if threads & (1 << thread_num):
                self._client.send_msg(f"PCEND {thread_num + 1}:")
                self._client.wait_recv(NEWLINE_MSG)

    def pc_kill(self, threads: int) -> None:
        """ Unloads aborted programs from selected pc threads """
        for thread_num in range(5):
            if threads & (1 << thread_num):
                self._client.send_msg(f"PCKILL {thread_num + 1}:")
                self._client.wait_recv(CONFIRMATION_REQUEST)
                self._client.send_msg("1\n")
                res = self._client.wait_recv(NEWLINE_MSG)
                if PROG_IS_ACTIVE in res:
                    raise KawaProgIsActive(thread_num + 1)

    def rcp_execute(self, program_name: str):
        self._client.send_msg("EXECUTE " + program_name)
        res = self._client.wait_recv(NEWLINE_MSG)

        if PROG_NOT_EXIST in res:
            raise KawaProgNotExistError(program_name)
        elif TEACH_MODE_ON in res:
            raise KawaTeachModeON
        elif TEACH_LOCK_ON in res:
            raise KawaTeachLockON
        elif MOTORS_DISABLED in res:
            raise KawaMotorsPoweredOFF

        self._client.wait_recv(PROGRAM_COMPLETED)

    def rcp_abort(self) -> None:
        self._client.send_msg("ABORT")
        self._client.wait_recv(NEWLINE_MSG)

    def kill_rcp(self) -> None:
        self._client.send_msg("KILL")
        self._client.wait_recv(CONFIRMATION_REQUEST)
        self._client.send_msg("1")
        self._client.wait_recv(NEWLINE_MSG)

    # def read_variable_real(self, variable_name: str) -> float:
    #     # -1000 - connection error
    #     # -1 - any error
    #
    #     self.robot_is_busy = True
    #
    #     self._client.sendall(b'list /r ' + bytes(str(variable_name), 'utf-8'))
    #     self._client.sendall(b'\x0a')
    #
    #     error_counter = 0
    #     while True:
    #         error_counter += 1
    #         receive_string = self._client.recv(4096, socket.MSG_PEEK)
    #         if receive_string.find(b'\x0d\x0a\x3e') > -1:
    #             tmp_string = self._client.recv(4096)
    #             break
    #
    #         if error_counter > error_counter_limit:
    #             print("Read variable CTE")
    #             self.add_to_log("Read variable CTE")
    #             self.close_connection()
    #             return -1000
    #
    #     real_variable = float(tmp_string.split()[-2])
    #     return real_variable
    #
    # def read_programs_list(self) -> [str]:
    #     self._client.sendall("DIRECTORY/P".encode())
    #     self._client.sendall(FOOTER_MSG)
    #
    #     kawasaki_msg = self._client.wait_recv([b'\x3e'])
    #     kawasaki_msg = kawasaki_msg.decode("utf-8", 'ignore')
    #
    #     response_strings = kawasaki_msg.split('\r\n')
    #     if len(response_strings) > 3:
    #         pg_list_str = response_strings[2]
    #         pg_list = [item.strip() for item in pg_list_str.split() if item.strip() != ""]
    #         return pg_list
    #


def pack_threads(*threads):
    return sum(1 << (thread_num - 1) for thread_num in threads)


if __name__ == "__main__":
    IP = "127.0.0.1"    # IP for K-Roset
    PORT = 9105         # Port for K-Roset

    robot = KHITelnetLib(IP, PORT)
    with open("../as_programs/endless.pc") as file:
        file_string = file.read()
        robot.upload_program(file_string, proceed_on_error=True)
        # robot.pc_execute("endless", 1)
    robot.get_rcp_status()
    robot.get_pc_status(63)
    # robot.pc_abort(63)
    robot.pc_kill(63)
    # with open("../as_programs/large.as") as file:
    #     file_string = file.read()
    #     robot.upload_program(file_string, proceed_on_error=True)
    #     robot.delete_program("large")
    robot.close_connection()
