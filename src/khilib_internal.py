import time

from telnet_client import TelnetClient
from robot_exception import *
import math
import socket

MAX_BYTES_TO_READ = 1024
error_counter_limit = 1000000


FOOTER_MSG = b"\n"
NEWLINE_MSG = b"\x0d\x0a\x3e"


class KHITelnetLib:
    def __init__(self, ip, port):
        self._ip_address = ip
        self._port_number = port

        self._client = TelnetClient(ip, port)
        self._connectionEstablished = False

        self.robot_is_busy = False

        if self.connect() != 1:
            raise RobotConnException()

    def connect(self):
        try:
            self._client.wait_recv(b"login")                   # Send 'as' as login for kawasaki telnet terminal
            self._client.send_msg("as", end=b"\x0d\x0a")  # Confirm with carriage return and line feed control symbols
            self._client.wait_recv(NEWLINE_MSG)                # wait for '>' symbol of a kawasaki terminal new line
        except (TimeoutError, ConnectionRefusedError):
            return 0
        return 1

    def handshake(self):
        """ Performs a handshake with the robot and raises an exception if something fails """
        self._client.send_msg("")                               # Send empty command
        if not self._client.wait_recv(NEWLINE_MSG):             # Wait for newline symbol
            raise RobotConnException()

    def ereset(self):
        self._client.send_msg("ERESET")
        self._client.wait_recv(NEWLINE_MSG)

    def close_connection(self):
        self.add_to_log("Close connection")
        self._client.disconnect()

    def robot_state(self) -> dict:
        """
        Checks various internal state variables of a Kawasaki robot and returns them as a dictionary.

        Returns:
            dict: A dictionary containing the following state variables:
                - 'motor_power' (bool): Current state of the motor power (ON/OFF).
                - 'cycle_start' (bool): State of the cycle start switch (ON/OFF).
                - 'repeat' (bool): State of the repeat switch (ON/OFF).
                - 'run' (bool): State of the run switch (ON/OFF).
                - 'error' (str / None): If an error is detected, the description of the error; otherwise, None.

        Raises:
            ---

        Note:
            This function sends commands to a Kawasaki robot via a client connection (`self._client`)
            to retrieve internal state variables and their descriptions, if available.
            Variables to check might be added via state_vars, where first element of tuple is
            a key in dictionary, and second - command that is sent to the robot
        """
        state = {}
        state_vars = (("motor_power", "SWITCH POWER"),
                      ("cycle_start", "SWITCH CS"),
                      ("cycle_start", "SWITCH RGSO"),
                      ("error", "SWITCH ERROR"),
                      ("repeat", "SWITCH REPEAT"),
                      ("run", "SWITCH RUN"))

        for var, msg in state_vars:
            self._client.send_msg(msg)
            res = True if self._client.wait_recv(NEWLINE_MSG).split()[-2].decode() == "ON" else False
            if var != "error":
                state.update({var: res})
                continue

            if res == "ON":
                self._client.send_msg("type $ERROR(ERROR)")
                error_descr = self._client.wait_recv(NEWLINE_MSG).decode()
                state.update({var: ' '.join(error_descr.split('\r\n')[1:-1])})
            else:
                state.update({var: None})
            continue
        return state


# ==========================================================================================

    def upload_program(self, program_name: str, program_string: str):
        #  None - everything is OK
        # -1 - uploading error
        # -2 - function arguments error
        # -1000 - communication with robot was aborted

        # Read file data and split to package
        # one package limit is 2918 byte (in KIDE)
        batch_size = 1500

        file = bytes(program_string, 'utf-8') + b'\x0d\x0a'
        num_packages = math.ceil(len(file) / batch_size)
        file_packages = []
        for idx in range(num_packages):
            pckg = b'\x02\x43\x20\x20\x20\x20\x30' + file[idx * batch_size:(idx + 1) * batch_size] + b'\x17'
            file_packages.append(pckg)

        status_rcp = self.status_rcp()
        if status_rcp['program_name'] == program_name:  # program active
            if status_rcp['program_status'] == 'Program running':  # program not aborted
                if self.abort_rcp(standalone=False) < 0:
                    return -1
            if self.kill_rcp(standalone=False) < 0:
                return -1

        self.robot_is_busy = True

        # Enable loading mode
        self._client.send_msg("LOAD using.rcc")

        tmp = bytes.fromhex('02 41 20 20 20 20 30 17')
        self._client.sendall(tmp)

        kawasaki_msg = self._client.wait_recv(b'Loading...(using.rcc)' + b'\x0d\x0a',         # package receive
                                                    b'\x65\x73\x73\x2e\x0d\x0a\x3e')  # End of 'SAVE/LOAD in progress.'

        if kawasaki_msg.find(b'\x65\x73\x73\x2e\x0d\x0a\x3e') >= 0:  # End of 'SAVE/LOAD in progress.'
            self.add_to_log("SAVE/LOAD in progress.")
            print("SAVE/LOAD in progress.")
            return -1

        # File transmission
        error_found = False
        resend_tries = 0

        for byte_package, package_num in zip(file_packages, range(len(file_packages))):
            self._client.send_bytes(byte_package)
            print("sending ", package_num, "/", num_packages)
            while True:
                try:
                    kawasaki_msg = self._client.wait_recv([b'\x72\x74\x29',                     # End of 'abort'
                                                   b'\x05\x02\x45\x17',                 # abort transmission
                                                   b'\x05\x02\x43\x17'])     # package receive
                except socket.timeout:
                    if resend_tries <= 10:
                        resend_tries += 1
                        print("Timeout error ", resend_tries, "/10 trying resending...")
                        self._client.send_bytes(byte_package)
                        continue
                    else:
                        print("Something's wrong")
                        self.add_to_log("Error sending program batch")
                        self._client.send_bytes(b'\x31\x0a')
                        error_found = True
                        break

                if kawasaki_msg.find(b'\x72\x74\x29') >= 0:
                    self.add_to_log("Error in program found")
                    self._client.sendall(b'\x31\x0a')  # 31 - discard program and delete
                    continue

                if kawasaki_msg.find(b'\x05\x02\x45\x17') >= 0:
                    error_found = True
                    break

                if kawasaki_msg.find(b'\x05\x02\x43\x17') >= 0:
                    break

            if error_found:
                break

        tmp = bytes.fromhex('02 43 20 20 20 20 30 1a 17')  # 9
        self._client.sendall(tmp)

        tmp = bytes.fromhex('02 45 20 20 20 20 30 17')  # Cancel loading mode
        self._client.sendall(tmp)

        input_buffer = b""
        while True:
            kawasaki_msg = self._client.wait_recv(b'\x72\x74\x29',                         # End of 'abort'
                                                  b'\x73\x29\x0d\x0a\x3e')     # End of 'errors'
            input_buffer += kawasaki_msg

            if kawasaki_msg.find(b'\x72\x74\x29') >= 0:
                self.add_to_log("Error in program found")
                self._client.sendall(b'\x31\x0a')  # 31 - discard program and delete
                continue

            if kawasaki_msg.find(b'\x73\x29\x0d\x0a\x3e') >= 0:
                break

        # split_message = input_buffer.decode("utf-8", 'ignore').split(" ")
        #
        # num_errors = 0
        # if len(split_message) > 2:
        #     num_errors = int(split_message[-2][-1:])
        # self.add_to_log("File load completed. ({0} errors)".format(num_errors))
        # if num_errors == 0:
        #     print("File transmission complete")
        #     self.robot_is_busy = False
        #     return None
        # else:
        #     print(f"{BColors.FAIL}File transmission not complete - Errors found{BColors.ENDC}")
        #     print("Errors list:")
        #     print(input_buffer.decode("utf-8", 'ignore'))
        #     print("Num errors:", num_errors)
        #     print("-----------------")

        self.robot_is_busy = False

        return -1

    def delete_program(self, program_name):
        self._client.sendall(("DELETE/P/D " + program_name).encode())
        self._client.sendall(FOOTER_MSG)

        self._client.wait_recv([b'\x30\x29\x20'])     # Are you sure ? (Yes:1, No:0)?

        self._client.sendall(b'\x31')
        self._client.sendall(FOOTER_MSG)

        self._client.wait_recv([b'\x31\x0d\x0a\x3e'])

    def status_pc(self, threads=None) -> [dict]:
        # -1000 - connection error
        # -1 - any error
        # return - list of dicts:
        # 'pc_status': 'Program running'/'Program is not running'
        # 'program_name': 'pg_name'/None

        threads_num = []
        if threads is None:  # Check all threads
            threads_num = [1, 2, 3, 4, 5]
        elif type(threads) == int:
            threads_num = [threads]
        elif type(threads) == list:
            for element in threads:
                if type(element) == int:
                    if (element <= 5) and (element > 0):
                        if element in threads_num:
                            print("The num. of thread is duplicating")
                            self.close_connection()
                            self.robot_is_busy = False
                            return -1
                        threads_num.append(element)
                    else:
                        print("Num of thread", element, "out of range: 1-5")
                        self.close_connection()
                        self.robot_is_busy = False
                        return -1
                else:
                    print("Num of thread should be int")
                    self.close_connection()
                    self.robot_is_busy = False
                    return -1
        else:
            print("Threads type is illegal")
            self.close_connection()
            self.robot_is_busy = False
            return -1
        self.robot_is_busy = True

        # receive_string = self.server.recv(4096)  # CLEAN ALL DATA IN BUFFER
        pc_status_list = [{}]*5

        for thread in threads_num:
            # PCSTATUS
            self._client.sendall(b'PCSTATUS ' + bytes(str(thread), 'utf-8') + b':')
            self._client.sendall(b'\x0a')

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self._client.recv(4096, socket.MSG_PEEK)
                # print("PCSTATUS", receive_string.decode("utf-8", 'ignore'), receive_string.hex())
                if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                    receive_string = self._client.recv(4096)
                    result_msg = receive_string.decode("utf-8", 'ignore')
                    break

                if error_counter > error_counter_limit:
                    print("PCSTATUS CTE")
                    self.add_to_log("PCSTATUS CTE")
                    self.close_connection()
                    return -1000

            status = {}
            response_list = result_msg.split('\r\n')

            for response_line in response_list:
                if response_line.find('PC status:') >= 0:
                    status.update({"pc_status": ' '.join(' '.join(response_line.split()).split(' ')[2:])[:-1]})

                if response_list[-2].find('No program is running.') >= 0:
                    status.update({"program_name": None})
                else:
                    status.update({"program_name": ''.join(response_list[-2].split(' ')[1].strip())})

            pc_status_list[thread-1] = status

        self.robot_is_busy = False

        return pc_status_list

    def abort_pc(self, *threads: int, program_name: str = "") -> [str]:
        # type(list) - [None, 'aborted', 'not_running', None, 'not_running']
        # None - if don't know about this process
        # 'aborted' - PC program aborted success
        # 'not_running' - PC program not running
        #
        # -1 - abort error
        # -1000 - communication error

        if program_name and len(threads) != 0:
            print("Error:")
            print("Abort program by name and by thread number doesn't support")
            return -1

        abort_num = []

        if program_name is None:
            if len(threads) is None:  # Check all threads
                abort_num = [1, 2, 3, 4, 5]
            elif len(threads) == 1:
                thread = threads[0]
                if (thread <= 5) and (thread > 0):
                    abort_num = [thread]
                else:
                    print("The num. of thread is out of range")
                    self.close_connection()
                    self.robot_is_busy = False
                    return -1

            else:
                for thread in threads:

                    if (thread <= 5) and (thread > 0):
                        if thread in abort_num:
                            print("The num. of thread is duplicating")
                            self.close_connection()
                            self.robot_is_busy = False
                            return -1
                        abort_num.append(thread)
                    else:
                        print("Num of thread", thread, "out of range: 1-5")
                        self.close_connection()
                        self.robot_is_busy = False
                        return -1

        else:  # Program name is not None
            pc_status = self.status_pc()
            for idx in range(len(pc_status)):
                process = pc_status[idx]
                if process['program_name'] == program_name:
                    abort_num.append(idx + 1)

        if not abort_num:
            print("PC program " + program_name + " not found")
            return -1

        self.robot_is_busy = True

        if self._handshake() < 0:
            return -1000

        # receive_string = self.server.recv(4096)  # CLEAN ALL DATA IN BUFFER
        pc_abort_list = [""] * 5

        for thread in abort_num:
            # PCABORT
            self._client.sendall(b'PCABORT ' + bytes(str(thread), "UTF-8") + b':')
            self._client.sendall(b'\x0a')

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self._client.recv(4096, socket.MSG_PEEK)
                # print("RCV", receive_string.decode("utf-8", 'ignore'), receive_string.hex())
                if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                    receive_string = self._client.recv(4096)
                    result_msg = receive_string.decode("utf-8", 'ignore')
                    break

                if error_counter > error_counter_limit:
                    print("PCABORT CTE")
                    self.add_to_log("PCABORT CTE")
                    self.close_connection()
                    return -1000

            if result_msg.find('PC program aborted.No') >= 0:
                pc_abort_list[thread - 1] = 'aborted'
            else:
                pc_abort_list[thread - 1] = 'not_running'

        return pc_abort_list

    def execute_pc(self, program_name: str, thread: int):
        #  Return:
        # 1 - everything is ok
        # -1000 - communication with robot was aborted

        if type(thread) == int:
            if (thread > 5) or (thread < 1):
                print("Error: Num of thread", thread, "out of range: 1-5")
                self.robot_is_busy = False
                return -1
        else:
            print("Error: Thread should be integer number")
            self.robot_is_busy = False
            return -1

        self.ereset()

        status = self.status_pc()
        kill_list = []
        for idx in range(len(status)):
            thread_status = status[idx]
            if thread_status['program_name'] == program_name:
                kill_list.append(idx + 1)

        if thread not in kill_list:
            kill_list.append(thread)

        self.abort_pc(*kill_list)
        self.kill_pc(*kill_list)

        self.robot_is_busy = True

        if self._handshake() < 0:
            return -1000

        # EXECUTE program
        self._client.sendall(b'PCEXECUTE ' + bytes(str(thread), 'utf-8') + b':' + program_name.encode())
        self._client.sendall(b'\x0a')

        while True:
            receive_string = self._client.recv(4096, socket.MSG_PEEK)
            # print(receive_string.decode("utf-8", 'ignore'), receive_string.hex())
            if receive_string.find(b'Program does not exist.') >= 0:
                # This is AS monitor terminal.. Wait '>' sign from robot
                receive_string = self._client.recv(4096)
                self.add_to_log("Program does not exist " + receive_string.decode("utf-8", 'ignore') +
                                ":" + receive_string.hex())
                print("Program " + program_name + " does not exist")

                self.robot_is_busy = False
                return -1

            if receive_string.find(b'\x0d\x0a\x3e') >= 0:  # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self._client.recv(4096)
                self.add_to_log("PC program run " + receive_string.decode("utf-8", 'ignore') +
                                ":" + receive_string.hex())
                print("PC " + program_name + " run")

                self.robot_is_busy = False
                return 1

    def kill_pc(self, *threads: int, program_name: str = ""):
        # type(list) - [None, 'killed', 'not_killed', None, None]
        # None - Don't know about this process
        # 'killed' - PC program killed success
        # 'not_running' - PC program not running
        #
        # -1 - illegal input parameters
        # -1000 - communication error

        if program_name and len(threads) != 0:
            print("Error: Kill program by name and by thread number doesn't support")
            return -1

        kill_num = []
        if not program_name:
            if threads is None:  # Check all threads
                kill_num = [1, 2, 3, 4, 5]
            elif len(threads) == 1:
                kill_num = threads
            else:
                for element in threads:
                    if type(element) == int:
                        if (element <= 5) and (element > 0):
                            if element in kill_num:
                                print("The num. of thread is duplicating")
                                self.close_connection()
                                self.robot_is_busy = False
                                return -1
                            kill_num.append(element)
                        else:
                            print("Num of thread", element, "out of range: 1-5")
                            self.close_connection()
                            self.robot_is_busy = False
                            return -1
                    else:
                        print("Num of thread should be int")
                        self.close_connection()
                        self.robot_is_busy = False
                        return -1
        else:
            pc_status = self.status_pc()
            for idx in range(len(pc_status)):
                process = pc_status[idx]
                if process['program_name'] == program_name:
                    kill_num.append(idx + 1)

        if not kill_num:
            print("PC program " + program_name + " not found")
            return -1

        self.robot_is_busy = True

        if self._handshake() < 0:
            return -1000

        # receive_string = self.server.recv(4096)  # CLEAN ALL DATA IN BUFFER
        pc_kill_list = [""] * 5

        for thread in kill_num:
            # PCKILL
            self._client.sendall(b'PCKILL ' + bytes(str(thread), "UTF-8") + b':')
            self._client.sendall(b'\x0a')

            error_counter = 0
            result_msg = b""

            while True:
                error_counter += 1
                receive_string = self._client.recv(4096, socket.MSG_PEEK)

                # print("RCV", receive_string.decode("utf-8", 'ignore'), receive_string.hex())

                if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                    receive_string = self._client.recv(4096)
                    result_msg = receive_string
                    break

                if receive_string.find(b'\x30\x29\x20') >= 0:  # Are you sure ? (Yes:1, No:0)?
                    self._client.recv(4096)
                    tmp = bytes.fromhex('31 0a')  # Delete program and abort
                    self._client.sendall(tmp)
                    continue

                if error_counter > error_counter_limit:
                    print("PCKILL CTE")
                    self.add_to_log("PCKILL CTE")
                    self.close_connection()
                    return -1000

            if result_msg.find(b'Cannot KILL program that is running.') >= 0:
                pc_kill_list[thread - 1] = 'not_killed'
            elif result_msg.find(b'\x31\x0d\x0a\x3e') >= 0:
                pc_kill_list[thread - 1] = 'killed'
            else:
                pc_kill_list[thread - 1] = 'unknown'

        return pc_kill_list

    def execute_rcp(self, program_name, wait_complete=False):
        #  Return:
        # 1 - program is run
        # 2 - program completed
        # -1000 - communication with robot was aborted

        if type(program_name) is not str:
            print("Program name isn't str. Abort")
            return -1

        self.ereset()

        status = self.status_rcp()

        if status['mode'] != 'REPEAT':
            print("Can't run program in not REPEAT mode")
            return -1

        if status['program_name'] is not None:
            if status['program_status'] != 'Program is not running':
                # abort rcp
                if self.abort_rcp(standalone=False) != 1:
                    print("Can't abort rcp program. Abort")
                    return -1
            if self.kill_rcp(standalone=False) != 1:
                print("Can't kill rcp program. Abort")
                return -1

        self.robot_is_busy = True

        if self._handshake() < 0:
            return -1000

        # ZPOW ON
        self._client.sendall(b'ZPOW ON')
        self._client.sendall(b'\x0a')

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self._client.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x0d\x0a\x3e') >= 0:  # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self._client.recv(4096)
                self.add_to_log("ZPOW ON " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                break
            if error_counter > error_counter_limit:
                self.add_to_log("ZPOW ON CTE")
                print("Execute - ZPOW ON error")
                self.close_connection()
                return -1000

        # EXECUTE program
        self._client.sendall(b'EXECUTE ' + program_name.encode())
        self._client.sendall(b'\x0a')

        input_buffer = b''
        while True:
            receive_string = self._client.recv(4096, socket.MSG_PEEK)
            # print(receive_string.decode("utf-8", 'ignore'), receive_string.hex())
            if receive_string.find(b'Program does not exist.') >= 0:
                receive_string = self._client.recv(4096)
                self.add_to_log("Program does not exist " + receive_string.decode("utf-8", 'ignore') +
                                ":" + receive_string.hex())
                print("Program " + program_name + " does not exist")

                self.robot_is_busy = False
                return -1

            if receive_string.find(b'(P1002)Cannot execute program because teach lock is ON.') > -1:
                receive_string = self._client.recv(4096)
                self.add_to_log("Pendant in teach mode " + receive_string.decode("utf-8", 'ignore') +
                                ":" + receive_string.hex())
                print("Pendant in teach mode")

                self.robot_is_busy = False
                return -1

            if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                tmp_buffer = self._client.recv(4096)
                input_buffer += tmp_buffer

                self.add_to_log("RCP program run " + receive_string.decode("utf-8", 'ignore') +
                                ":" + receive_string.hex())
                print("RCP " + program_name + " run")

                if not wait_complete:
                    self.robot_is_busy = False
                    return 1

            if (input_buffer + receive_string).find(b'Program completed.No = 1') > -1:
                tmp_buffer = self._client.recv(4096)
                input_buffer += tmp_buffer

                self.add_to_log("RCP program completed " + receive_string.decode("utf-8", 'ignore') +
                                ":" + input_buffer.hex())
                print("RCP " + program_name + " completed")

                self.robot_is_busy = False
                return 2

    def status_rcp(self) -> dict:
        status = {}

        self.robot_is_busy = True

        self.send_msg(b'STATUS')
        result_msg = self._client.wait_recv([b'\x0d\x0a\x3e'])

        if result_msg is not None:
            if len(result_msg) > 10:
                result_msg = result_msg.decode("utf-8", 'ignore')
                response_list = result_msg.split('\r\n')

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

                self.robot_is_busy = False

                print(status)
                return status

        self.robot_is_busy = False

    def abort_rcp(self, standalone=True):
        if standalone:
            self.robot_is_busy = True

        self._client.sendall("ABORT".encode())
        self._client.sendall(FOOTER_MSG)

        self._client.wait_recv([b'ABORT' + b'\x0d\x0a\x3e'])

        if standalone:
            self.robot_is_busy = False

        return 1

    def kill_rcp(self, standalone=True):
        if standalone:
            self.robot_is_busy = True

        self._client.sendall("KILL".encode())
        self._client.sendall(FOOTER_MSG)

        self._client.wait_recv([b'\x3a\x30\x29\x20'])  # END (Yes:1, No:0)

        self._client.sendall(b'\x31\x0a')  # Delete program and abort

        self._client.wait_recv([b'\x31\x0d\x0a\x3e'])

        if standalone:
            self.robot_is_busy = False

        return 1

    def read_variable_real(self, variable_name: str) -> float:
        # -1000 - connection error
        # -1 - any error

        self.robot_is_busy = True

        self._client.sendall(b'list /r ' + bytes(str(variable_name), 'utf-8'))
        self._client.sendall(b'\x0a')

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self._client.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x0d\x0a\x3e') > -1:
                tmp_string = self._client.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("Read variable CTE")
                self.add_to_log("Read variable CTE")
                self.close_connection()
                return -1000

        real_variable = float(tmp_string.split()[-2])
        return real_variable

    def read_programs_list(self) -> [str]:
        self._client.sendall("DIRECTORY/P".encode())
        self._client.sendall(FOOTER_MSG)

        kawasaki_msg = self._client.wait_recv([b'\x3e'])
        kawasaki_msg = kawasaki_msg.decode("utf-8", 'ignore')

        response_strings = kawasaki_msg.split('\r\n')
        if len(response_strings) > 3:
            pg_list_str = response_strings[2]
            pg_list = [item.strip() for item in pg_list_str.split() if item.strip() != ""]
            return pg_list

    def _handshake(self):
        # 1 - without errors
        # -1000 - connection errors and abort

        self._client.sendall(b'\x0a')
        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self._client.recv(4096, socket.MSG_PEEK)

            if receive_string.find(b'\x0d\x0a\x3e') > -1:
                self._client.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("Handshake error")
                self.close_connection()
                return -1000
        return 1

    def add_to_log(self, msg):
        #print(msg)  # TODO: перенести логирование в верхний уровень
        pass


if __name__ == "__main__":
    IP = "127.0.0.1"    # IP for K-Roset
    PORT = 9105         # Port for K-Roset

    robot = KHITelnetLib(IP, PORT)
    print(robot.robot_state())
    robot.close_connection()
