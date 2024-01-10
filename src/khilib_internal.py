import math
import time
from utils.robot_state import RobotState, ROBOT_STATE_VARS
from utils.pc_thread_state import ThreadState
from telnet_client import TelnetClient
from robot_exception import *


# One package size in bytes for splitting large programs. Slightly faster at higher values
# It's 2962 bytes in KIDE and robot is responding for up to 3064 bytes
UPLOAD_BATCH_SIZE = 1000

error_counter_limit = 1000000

NEWLINE_MSG = b"\x0d\x0a\x3e"                      # "\r\n>" - Message when clearing terminal

START_LOADING = b"LOAD using.rcc\n" + bytes.fromhex('02 41 20 20 20 20 30 17')
CANCEL_LOADING = bytes.fromhex('02 43 20 20 20 20 30 1a 17 02 45 20 20 20 20 30 17')
PKG_RECV = b"\x05\x02\x43\x17"                     # Byte sequence when program batch is accepted
SYNTAX_ERROR = "\r\nSTEP syntax error.\r\n(0:Change to comment and continue, 1:Delete program and abort)\r\n".encode()
CONFIRM_TRANSMISSION = b"\x73\x29\x0d\x0a\x3e"      # end of "N errors)"
SAVE_LOAD_ERROR = b"\x65\x73\x73\x2e\x0d\x0a\x3e"  # Byte sequence when previous save/load operation was interrupted
HARD_ABORT = b"\x05\x02\x45\x17"                   #
CONFIRMATION_REQUEST = b'\x30\x29\x20'             # Are you sure ? (Yes:1, No:0)?

NOT_EXIST_ERR = "Program does not exist.".encode()


class KHITelnetLib:
    def __init__(self, ip, port):
        self._ip_address = ip
        self._port_number = port
        self._client = TelnetClient(ip, port)

        self.robot_is_busy = False
        self._connect()

    def _connect(self):
        try:
            self._client.wait_recv(b"login")              # Send 'as' as login for kawasaki telnet terminal
            self._client.send_msg("as")                   # Confirm with carriage return and line feed control symbols
            self._client.wait_recv(NEWLINE_MSG)           # wait for '>' symbol of a kawasaki terminal new line
        except (TimeoutError, ConnectionRefusedError):
            raise KawaConnError()

    def handshake(self):
        """ Performs a handshake with the robot and raises an exception if something fails """
        self._client.send_msg("")                         # Send empty command
        if not self._client.wait_recv(NEWLINE_MSG):       # Wait for newline symbol
            raise KawaConnError()

    def ereset(self):
        self._client.send_msg("ERESET")
        self._client.wait_recv(NEWLINE_MSG)

    def close_connection(self):
        self._client.disconnect()

    def get_system_switch_state(self, switch_name: str) -> bool:
        """ Sets robot system switch state """
        self._client.send_msg("SWITCH " + switch_name)
        return self._client.wait_recv(NEWLINE_MSG).split()[-2].decode() == "ON"

    def set_system_switch_state(self, switch_name: str, value: bool):
        """ Sets robot system switch. Note that switch might be read-only,
            in that case switch value won't be changed """
        self._client.send_msg(switch_name + "ON" if value else "OFF")
        self._client.wait_recv(NEWLINE_MSG)

    def get_error_descr(self):
        """ Returns robot error state description, empty string if no error """
        self._client.send_msg("type $ERROR(ERROR)")
        res = self._client.wait_recv(NEWLINE_MSG).decode()
        if "Value is out of range." not in res:
            return ' '.join(res.split('\r\n')[1:-1])
        return ""

    def get_pc_status(self, threads: int) -> [ThreadState]:
        """ Checks the running status of a list of PC programs based on a packed integer representing threads to check.

        Args:
            threads (int): An integer representing the threads to be checked for status. The first five bits
                correspond to the threads: bit 0 represents thread 1, bit 1 represents thread 2, and so on.
                A set bit (1) means the corresponding thread's status will be checked.

        Returns:
            list[dict]: A list containing dictionaries, each representing the status of a thread.
            Each dictionary includes following information:
             - Program name (str): Name of running program or "No" if no program is running
             - Running (bool)
             - Completed cycles (int)
             - Remaining cycles (int)
        Note:
            This method is considered to be low-level and is called from another class where
            input validation and packing is done, but for testing it can be called directly
            with help of utility function "pack_threads(*args)" provided in this module
        """
        # TODO: Check of works
        pc_status_list = [ThreadState for _ in range(5)]
        for thread in range(5):
            if threads & (1 << thread):  # Unpack threads from 5-bit integer representation
                self._client.send_msg(f"PCSTATUS {thread + 1}:")
                status = self._client.wait_recv(NEWLINE_MSG).decode().split("\r\n")[1:]   # Split by newlines
                pc_status_list[thread].name = status[-2].split()[0]                       # Get program name
                split = [" ".join(el.split()).split(": ") for el in status if ":" in el]  # Get lines like "key: value"
                for key, value in split:
                    if "PC status" in key:
                        pc_status_list[thread].running = "not running" not in value
                        continue
                    pc_status_list[thread].__setattr__(key, value)
        return pc_status_list

    def get_rcp_status(self) -> dict:
        status = {}
        self._client.send_msg("STATUS")
        if (result_msg := self._client.wait_recv(NEWLINE_MSG)) and len(result_msg) > 10:
            response_list = result_msg.decode().split('\r\n')

            for response_line in response_list:
                if response_line.find(' mode') >= 0:
                    status.update({"mode": response_line.split(' ')[0]})

                if response_line.find('Stepper status:') >= 0:
                    status.update({"program_status": ' '.join(response_line.split(' ')[2:]).strip()[:-1]})

            if response_list[-2].find('No program is running.') >= 0:
                status.update({"program_name": None})
                status.update({"step_num": None})
            else:
                status.update({"program_name": ''.join(response_list[-2].split(' ')[1].strip())})
                status.update({"step_num": response_list[-2].split()[2]})
        return status

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
        """
        program_bytes = bytes(program_string, "utf-8")
        num_packages = math.ceil(len(program_bytes) / UPLOAD_BATCH_SIZE)
        file_packages = [
            (b"\x02\x43\x20\x20\x20\x20\x30"
             + program_bytes[idx * UPLOAD_BATCH_SIZE: (idx + 1) * UPLOAD_BATCH_SIZE] + b"\x17")
            for idx in range(num_packages)
        ]

        self._client.send_bytes(START_LOADING)

        if SAVE_LOAD_ERROR in self._client.wait_recv(b'Loading...(using.rcc)\r\n', SAVE_LOAD_ERROR):
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
                break

        self._client.send_bytes(CANCEL_LOADING)
        self._client.wait_recv(CONFIRM_TRANSMISSION)

        if errors_string:
            raise KawaProgSyntaxError(errors_string.split(SYNTAX_ERROR))

    def delete_program(self, program_name: str) -> None:
        self._client.send_msg("DELETE/P/D " + program_name)
        self._client.wait_recv(CONFIRMATION_REQUEST)
        self._client.send_msg("1")
        self._client.wait_recv(b"1" + NEWLINE_MSG)

    def execute_pc(self, program_name: str, thread: int) -> None:
        """ Executes PC program on selected thread
        Args:
             program_name (str): Name of a PC program inside robot's memory to be executed
             thread (int): PC program thread
        """
        self._client.send_msg(f"PCEXECUTE {str(thread)}: {program_name}")
        if NOT_EXIST_ERR in self._client.wait_recv(NEWLINE_MSG, NOT_EXIST_ERR):
            raise KawaProgNotExistError(program_name)

    def abort_pc(self, threads: int) -> None:
        """ Aborts running PC programs on selected threads.
        Args: threads (int): An integer representing the threads to be checked for status.
                             See "status_pc" for more info
        """
        for thread in range(5):
            if threads & (1 << thread):
                self._client.send_msg(f"PCABORT {thread + 1}:")
                self._client.wait_recv(NEWLINE_MSG)

    def kill_pc(self, threads: int):
        for thread in range(5):
            if threads & (1 << thread):
                self._client.send_msg(f"PCKILL {thread + 1}:")
                response = self._client.wait_recv(NEWLINE_MSG, CONFIRMATION_REQUEST)
                if CONFIRMATION_REQUEST in response:
                    self._client.send_msg("1\n")

                if result_msg.find(b'Cannot KILL program that is running.') >= 0:
                    pc_kill_list[thread - 1] = 'not_killed'
                elif b"1" + NEWLINE_MSG in response:
                    pc_kill_list[thread - 1] = 'killed'
                else:
                    pc_kill_list[thread - 1] = 'unknown'

        return pc_kill_list
    #
    # def execute_rcp(self, program_name, wait_complete=False):
    #     #  Return:
    #     # 1 - program is run
    #     # 2 - program completed
    #     # -1000 - communication with robot was aborted
    #
    #     if type(program_name) is not str:
    #         print("Program name isn't str. Abort")
    #         return -1
    #
    #     self.ereset()
    #
    #     status = self.status_rcp()
    #
    #     if status['mode'] != 'REPEAT':
    #         print("Can't run program in not REPEAT mode")
    #         return -1
    #
    #     if status['program_name'] is not None:
    #         if status['program_status'] != 'Program is not running':
    #             # abort rcp
    #             if self.abort_rcp(standalone=False) != 1:
    #                 print("Can't abort rcp program. Abort")
    #                 return -1
    #         if self.kill_rcp(standalone=False) != 1:
    #             print("Can't kill rcp program. Abort")
    #             return -1
    #
    #     self.robot_is_busy = True
    #
    #     if self._handshake() < 0:
    #         return -1000
    #
    #     # ZPOW ON
    #     self._client.sendall(b'ZPOW ON')
    #     self._client.sendall(b'\x0a')
    #
    #     error_counter = 0
    #     while True:
    #         error_counter += 1
    #         receive_string = self._client.recv(4096, socket.MSG_PEEK)
    #         if receive_string.find(b'\x0d\x0a\x3e') >= 0:  # This is AS monitor terminal..  Wait '>' sign from robot
    #             receive_string = self._client.recv(4096)
    #             self.add_to_log("ZPOW ON " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
    #             break
    #         if error_counter > error_counter_limit:
    #             self.add_to_log("ZPOW ON CTE")
    #             print("Execute - ZPOW ON error")
    #             self.close_connection()
    #             return -1000
    #
    #     # EXECUTE program
    #     self._client.sendall(b'EXECUTE ' + program_name.encode())
    #     self._client.sendall(b'\x0a')
    #
    #     input_buffer = b''
    #     while True:
    #         receive_string = self._client.recv(4096, socket.MSG_PEEK)
    #         # print(receive_string.decode("utf-8", 'ignore'), receive_string.hex())
    #         if receive_string.find(b'Program does not exist.') >= 0:
    #             receive_string = self._client.recv(4096)
    #             self.add_to_log("Program does not exist " + receive_string.decode("utf-8", 'ignore') +
    #                             ":" + receive_string.hex())
    #             print("Program " + program_name + " does not exist")
    #
    #             self.robot_is_busy = False
    #             return -1
    #
    #         if receive_string.find(b'(P1002)Cannot execute program because teach lock is ON.') > -1:
    #             receive_string = self._client.recv(4096)
    #             self.add_to_log("Pendant in teach mode " + receive_string.decode("utf-8", 'ignore') +
    #                             ":" + receive_string.hex())
    #             print("Pendant in teach mode")
    #
    #             self.robot_is_busy = False
    #             return -1
    #
    #         if receive_string.find(b'\x0d\x0a\x3e') >= 0:
    #             tmp_buffer = self._client.recv(4096)
    #             input_buffer += tmp_buffer
    #
    #             self.add_to_log("RCP program run " + receive_string.decode("utf-8", 'ignore') +
    #                             ":" + receive_string.hex())
    #             print("RCP " + program_name + " run")
    #
    #             if not wait_complete:
    #                 self.robot_is_busy = False
    #                 return 1
    #
    #         if (input_buffer + receive_string).find(b'Program completed.No = 1') > -1:
    #             tmp_buffer = self._client.recv(4096)
    #             input_buffer += tmp_buffer
    #
    #             self.add_to_log("RCP program completed " + receive_string.decode("utf-8", 'ignore') +
    #                             ":" + input_buffer.hex())
    #             print("RCP " + program_name + " completed")
    #
    #             self.robot_is_busy = False
    #             return 2
    #
    # def abort_rcp(self, standalone=True):
    #     if standalone:
    #         self.robot_is_busy = True
    #
    #     self._client.sendall("ABORT".encode())
    #     self._client.sendall(FOOTER_MSG)
    #
    #     self._client.wait_recv([b'ABORT' + b'\x0d\x0a\x3e'])
    #
    #     if standalone:
    #         self.robot_is_busy = False
    #
    #     return 1
    #
    # def kill_rcp(self, standalone=True):
    #     if standalone:
    #         self.robot_is_busy = True
    #
    #     self._client.sendall("KILL".encode())
    #     self._client.sendall(FOOTER_MSG)
    #
    #     self._client.wait_recv([b'\x3a\x30\x29\x20'])  # END (Yes:1, No:0)
    #
    #     self._client.sendall(b'\x31\x0a')  # Delete program and abort
    #
    #     self._client.wait_recv([b'\x31\x0d\x0a\x3e'])
    #
    #     if standalone:
    #         self.robot_is_busy = False
    #
    #     return 1
    #
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
    # def _handshake(self):
    #     # 1 - without errors
    #     # -1000 - connection errors and abort
    #
    #     self._client.sendall(b'\x0a')
    #     error_counter = 0
    #     while True:
    #         error_counter += 1
    #         receive_string = self._client.recv(4096, socket.MSG_PEEK)
    #
    #         if receive_string.find(b'\x0d\x0a\x3e') > -1:
    #             self._client.recv(4096)
    #             break
    #
    #         if error_counter > error_counter_limit:
    #             print("Handshake error")
    #             self.close_connection()
    #             return -1000
    #     return 1
    #
    # def add_to_log(self, msg):
    #     #print(msg)  # TODO: перенести логирование в верхний уровень
    #     pass


def pack_threads(*threads):
    return sum(1 << (thread - 1) for thread in threads)


if __name__ == "__main__":
    IP = "127.0.0.1"    # IP for K-Roset
    PORT = 9105         # Port for K-Roset

    robot = KHITelnetLib(IP, PORT)
    with open("../as_programs/large.as") as file:
        file_string = file.read()
        robot.upload_program(file_string, proceed_on_error=True)
        robot.delete_program("large")
    robot.close_connection()
