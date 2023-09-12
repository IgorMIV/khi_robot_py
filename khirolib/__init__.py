import socket
import select
import time
import math
import threading

error_counter_limit = 1000000
footer_message = bytes.fromhex('0a')
timer_period = 0.1


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class khirolib():
    def __init__(self, ip, port, log=False):
        self.ip_address = ip
        self.port_number = port
        self.logging = log
        self.server = None

        self._connectionEstablished = False

        self.command_buffer = None
        self.input_buffer = b''

        if self.logging:
            self.logfile = open("log.txt", "w")
            self.logfile.write(str(time.time()) + ":" + "Log started" + '\n')

        self.robot_is_busy = False

        if self.connect() != 1:
            print("Can't establish connection with robot")
        else:
            self.timer = threading.Timer(timer_period, self.timer_timeout)
            self.timer.start()
            self._connectionEstablished = True

    def timer_timeout(self):
        if self.command_buffer is not None:
            if self.command_buffer == '':
                self.server.sendall(footer_message)
            else:
                self.server.sendall(self.command_buffer)
                self.server.sendall(footer_message)

            self.command_buffer = None

        self.input_buffer += self.read_input_buffer()

        self.timer = threading.Timer(timer_period, self.timer_timeout)
        self.timer.start()

    def add_cmd_to_buffer(self, cmd):
        if self.command_buffer is not None:
            self.command_buffer += cmd
        else:
            self.command_buffer = cmd

    def connect(self):
        #     #  Return:
        #     # 1 - without errors
        #     # -1000 - communication with robot was aborted

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.connect((self.ip_address, self.port_number))

        kawasaki_msg = self.wait_recv([b'login:'], timeout=1)
        # self.parent.print_text(kawasaki_msg.decode("utf-8", 'ignore'))

        self.server.sendall(b'as')
        self.server.sendall(b'\x0d\x0a')

        kawasaki_msg = self.wait_recv([b'\x3e'], timeout=1)
        # self.parent.print_text(kawasaki_msg.decode("utf-8", 'ignore'))

        return 1

    def send_command(self, command):
        self.add_cmd_to_buffer(command.encode())
        self.add_cmd_to_buffer(footer_message)
        # self.command_buffer = command

    def read_input_buffer(self):
        timeout = 0.01
        MAX_BYTES_TO_READ = 1024
        incoming = b''
        try:
            ready_to_read, ready_to_write, in_error = select.select([self.server, ], [], [], timeout)
        except select.error:
            print('Transmission error')
            return None
        else:
            if len(in_error) > 0:
                print('Transmission error')
                return None
            if len(ready_to_read) > 0:
                try:
                    incoming = self.server.recv(MAX_BYTES_TO_READ)
                except:
                    print('Transmission error')
        return incoming

    def read_recv(self, ends_list):
        for eom in ends_list:
            eom_pos = self.input_buffer.find(eom)
            if eom_pos > -1:  # Wait eom message from robot
                res_string = self.input_buffer[:eom_pos+len(eom)]
                self.input_buffer = self.input_buffer[eom_pos+len(eom):]
                return res_string

    def wait_recv(self, ends_list, timeout=0.01):
        break_actual = False
        while True:
            try:
                ready_to_read, ready_to_write, in_error = select.select([self.server, ], [], [], timeout)
            except select.error:
                print('Transmission error')
            else:
                if len(in_error) > 0:
                    print('Transmission error')
                    return -1
                if len(ready_to_read) > 0:
                    incoming = b''
                    while True:
                        if break_actual:
                            break
                        try:
                            recv = self.server.recv(1)
                        except:
                            print('Transmission error')
                            break_actual = True
                            break
                        if recv == b'':
                            break
                        incoming += recv
                        # print("INC", incoming)
                        # print("INC", incoming.hex())
                        for eom in ends_list:
                            if incoming.find(eom) > -1:     # Wait eom message from robot
                                break_actual = True
                                break
            if break_actual:
                break
        # print(incoming)
        return incoming

    def is_connection_established(self):
        return self._connectionEstablished

    def disconnect(self):
        if self.server is not None:
            self.timer.cancel()
            self.close_connection()
            self._connectionEstablished = False

    def close_connection(self):
        self.add_to_log("Close connection")
        self.server.close()

    def ereset(self):
        # # 1 - everything is ok
        # # -1000 - communication with robot was aborted
        command = "ERESET"
        self.server.sendall(command.encode())
        self.server.sendall(footer_message)

        kawasaki_msg = self.wait_recv([b'\x3e'], timeout=1)
        print(kawasaki_msg.decode("utf-8", 'ignore'))
        # self.parent.print_text(kawasaki_msg.decode("utf-8", 'ignore'))

    def upload_program(self, filename=None, program_name=None, program_text=None):
        #  None - everything is OK
        # -1 - uploading error
        # -2 - function arguments error
        # -1000 - communication with robot was aborted

        if filename is None:
            if (program_name is None) or (program_text is None):
                self.add_to_log("Error 1")
                print("You should set correct function arguments")
                return -2
        else:
            if (program_name is not None) or (program_text is not None):
                self.add_to_log("Error 2")
                print("You couldn't use loading from file and from string in the same time")
                return -2

        # Read file data and split to package
        # one package limit is 2918 byte (in KIDE)
        if filename is not None:
            f = open(filename, "r")
            first_line = f.readline()
            file_string = first_line + f.read()
            program_name = first_line.split(' ')[1].split('(')[0]
        else:
            file_string = '.PROGRAM ' + program_name + '\n'
            file_string += program_text + '\n'
            file_string += '.END' + '\n'

        file = bytes(file_string, 'utf-8') + b'\x0d\x0a'
        num_packages = math.ceil(len(file) / 2910)
        file_packages = []
        for i in range(num_packages):
            pckg = b'\x02\x43\x20\x20\x20\x20\x30' + file[i * 2910:(i + 1) * 2910] + b'\x17'
            file_packages.append(pckg)

        status_rcp = self.status_rcp()
        if status_rcp['program_name'] == program_name:  # program active
            if status_rcp['program_status'] == 'Program running':  # program not aborted
                if self.abort_rcp(standalone=False) < 0:
                    return -1
            if self.kill_rcp(standalone=False) < 0:
                return -1

        # status_pc_list = self.status_pc()
        # for i in range(len(status_pc_list)):
        #     status_pc = status_pc_list[i]
        #     if status_pc['program_name'] == program_name:
        #         if status_pc['pc_status'] == 'Program running':
        #             if self.abort_pc(threads=i+1)[i] is None:
        #                 print("Abort failure")
        #                 return -1
        #         self.kill_pc(threads=i+1)
        #         # if self.kill_pc(program_name=program_name) < 0:
        #         #     return -1

        self.robot_is_busy = True

        # Enable loading mode
        self.server.sendall("LOAD using.rcc".encode())
        self.server.sendall(footer_message)

        tmp = bytes.fromhex('02 41 20 20 20 20 30 17')
        self.server.sendall(tmp)

        kawasaki_msg = self.wait_recv([b'Loading...(using.rcc)' + b'\x0d\x0a',         # package receive
                                       b'\x65\x73\x73\x2e\x0d\x0a\x3e'], timeout=1)    # End of 'SAVE/LOAD in progress.'

        if kawasaki_msg.find(b'\x65\x73\x73\x2e\x0d\x0a\x3e') >= 0:  # End of 'SAVE/LOAD in progress.'
            self.add_to_log("SAVE/LOAD in progress.")
            print("SAVE/LOAD in progress.")
            return -1

        # File transmission
        error_not_found = True
        for byte_package in file_packages:
            if error_not_found:
                self.server.sendall(byte_package)

                while True:
                    kawasaki_msg = self.wait_recv([b'\x72\x74\x29',                     # End of 'abort)'
                                                   b'\x05\x02\x45\x17',                 # abort transmission
                                                   b'\x05\x02\x43\x17'], timeout=1)     # package receive

                    if kawasaki_msg.find(b'\x72\x74\x29') >= 0:
                        self.add_to_log("Error in program found")
                        self.server.sendall(b'\x31\x0a')  # 31 - discard program and delete
                        continue

                    if kawasaki_msg.find(b'\x05\x02\x45\x17') >= 0:
                        error_not_found = False
                        break

                    if kawasaki_msg.find(b'\x05\x02\x43\x17') >= 0:
                        break

        tmp = bytes.fromhex('02 43 20 20 20 20 30 1a 17')  # 9
        self.server.sendall(tmp)

        tmp = bytes.fromhex('02 45 20 20 20 20 30 17')  # Cancel loading mode
        self.server.sendall(tmp)

        input_buffer = ""
        while True:
            kawasaki_msg = self.wait_recv([b'\x72\x74\x29',                         # End of 'abort)'
                                           b'\x73\x29\x0d\x0a\x3e'], timeout=1)     # End of 'errors)'
            input_buffer += kawasaki_msg.decode("utf-8", 'ignore')

            if kawasaki_msg.find(b'\x72\x74\x29') >= 0:
                self.add_to_log("Error in program found")
                self.server.sendall(b'\x31\x0a')  # 31 - discard program and delete
                continue

            if kawasaki_msg.find(b'\x73\x29\x0d\x0a\x3e') >= 0:
                self.add_to_log("File load completed. (n errors)")
                break

        split_message = input_buffer.split(" ")

        if len(split_message) > 2:
            num_errors = int(split_message[-2][1:])

        if num_errors == 0:
            print("File transmission complete")
            self.robot_is_busy = False

            return None
        else:
            print(f"{bcolors.FAIL}File transmission not complete - Errors found{bcolors.ENDC}")
            print("Errors list:")
            print(input_buffer.decode("utf-8", 'ignore'))
            print("Num errors:", num_errors)
            print("-----------------")

        self.robot_is_busy = False

        return -1

    def delete_program(self, program_name):
        self.server.sendall(("DELETE/P/D " + program_name).encode())
        self.server.sendall(footer_message)

        kawasaki_msg = self.wait_recv([b'\x30\x29\x20'], timeout=1)     # Are you sure ? (Yes:1, No:0)?

        self.server.sendall(b'\x31')
        self.server.sendall(footer_message)

        kawasaki_msg = self.wait_recv([b'\x31\x0d\x0a\x3e'], timeout=1)

    def status_pc(self, threads=None):
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
                            self.abort_connection()
                            self.robot_is_busy = False
                            return -1
                        threads_num.append(element)
                    else:
                        print("Num of thread", element, "out of range: 1-5")
                        self.abort_connection()
                        self.robot_is_busy = False
                        return -1
                else:
                    print("Num of thread should be int")
                    self.abort_connection()
                    self.robot_is_busy = False
                    return -1
        else:
            print("Threads type is illegal")
            self.abort_connection()
            self.robot_is_busy = False
            return -1
        self.robot_is_busy = True

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        # receive_string = self.server.recv(4096)  # CLEAN ALL DATA IN BUFFER
        pc_status_list = [None]*5

        for thread in threads_num:
            # PCSTATUS
            self.server.sendall(b'PCSTATUS ' + bytes(str(thread), 'utf-8') + b':')
            self.server.sendall(b'\x0a')

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                # print("PCSTATUS", receive_string.decode("utf-8", 'ignore'), receive_string.hex())
                if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    result_msg = receive_string.decode("utf-8", 'ignore')
                    break

                if error_counter > error_counter_limit:
                    print("PCSTATUS CTE")
                    self.add_to_log("PCSTATUS CTE")
                    self.abort_connection()
                    return -1000

                if self.abort_operation:
                    self.abort_connection()
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

        if self.connection_mode == 'single':
            self.close_connection()

        self.robot_is_busy = False

        return pc_status_list

    def abort_pc(self, program_name=None, threads=None):
        # type(list) - [None, 'aborted', 'not_running', None, 'not_running']
        # None - if don't know about this process
        # 'aborted' - PC program aborted success
        # 'not_running' - PC program not running
        #
        # -1 - abort error
        # -1000 - communication error

        if (program_name is not None) and (threads is not None):
            print(f"{bcolors.FAIL}Error:{bcolors.ENDC}")
            print("Abort program by name and by thread number doesn't support")
            return -1

        abort_num = []

        if program_name is None:
            if threads is None:  # Check all threads
                abort_num = [1, 2, 3, 4, 5]
            elif type(threads) == int:
                if (threads <= 5) and (threads > 0):
                    abort_num = [threads]
                else:
                    print("The num. of thread is out of range")
                    self.abort_connection()
                    self.robot_is_busy = False
                    return -1

            elif type(threads) == list:
                for element in threads:
                    if type(element) == int:
                        if (element <= 5) and (element > 0):
                            if element in abort_num:
                                print("The num. of thread is duplicating")
                                self.abort_connection()
                                self.robot_is_busy = False
                                return -1
                            abort_num.append(element)
                        else:
                            print("Num of thread", element, "out of range: 1-5")
                            self.abort_connection()
                            self.robot_is_busy = False
                            return -1
                    else:
                        print("Num of thread should be int")
                        self.abort_connection()
                        self.robot_is_busy = False
                        return -1
            else:
                print("Threads type is illegal")
                self.abort_connection()
                self.robot_is_busy = False
                return -1
        else:  # Program name is not None
            pc_status = self.status_pc()
            for i in range(len(pc_status)):
                process = pc_status[i]
                if process['program_name'] == program_name:
                    abort_num.append(i+1)

        if not abort_num:
            print(f"{bcolors.FAIL}" + "PC program " + program_name + " not found" + f"{bcolors.ENDC}")
            return -1

        self.robot_is_busy = True

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        if self._handshake() < 0:
            return -1000

        # receive_string = self.server.recv(4096)  # CLEAN ALL DATA IN BUFFER
        pc_abort_list = [None] * 5

        for thread in abort_num:
            # PCABORT
            self.server.sendall(b'PCABORT ' + bytes(str(thread), "UTF-8") + b':')
            self.server.sendall(b'\x0a')

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                # print("RCV", receive_string.decode("utf-8", 'ignore'), receive_string.hex())
                if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    result_msg = receive_string.decode("utf-8", 'ignore')
                    break

                if error_counter > error_counter_limit:
                    print("PCABORT CTE")
                    self.add_to_log("PCABORT CTE")
                    self.abort_connection()
                    return -1000

                if self.abort_operation:
                    self.abort_connection()
                    return -1000

            if result_msg.find('PC program aborted.No') >= 0:
                pc_abort_list[thread-1] = 'aborted'
            else:
                pc_abort_list[thread - 1] = 'not_running'

        return pc_abort_list

    def execute_pc(self, program_name, thread):
        #  Return:
        # 1 - everything is ok
        # -1000 - communication with robot was aborted

        if type(thread) == int:
            if (thread > 5) or (thread < 1):
                print(f"{bcolors.FAIL}Error:{bcolors.ENDC}")
                print("Num of thread", thread, "out of range: 1-5")
                self.robot_is_busy = False
                return -1
        else:
            print(f"{bcolors.FAIL}Error:{bcolors.ENDC}")
            print("Thread should be integer number")
            self.robot_is_busy = False
            return -1

        self.ereset()

        status = self.status_pc()
        kill_list = []
        for i in range(len(status)):
            thread_status = status[i]
            if thread_status['program_name'] == program_name:
                kill_list.append(i+1)

        if thread not in kill_list:
            kill_list.append(thread)

        self.abort_pc(threads=kill_list)
        self.kill_pc(threads=kill_list)

        self.robot_is_busy = True
        self.abort_operation = False

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        if self._handshake() < 0:
            return -1000

        # EXECUTE program
        self.server.sendall(b'PCEXECUTE ' + bytes(str(thread), 'utf-8') + b':' + program_name.encode())
        self.server.sendall(b'\x0a')

        while True:
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            # print(receive_string.decode("utf-8", 'ignore'), receive_string.hex())
            if receive_string.find(b'Program does not exist.') >= 0:  # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self.server.recv(4096)
                self.add_to_log("Program does not exist " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                print(f"{bcolors.FAIL}" + "Program " + program_name + " does not exist" + f"{bcolors.ENDC}")

                if self.connection_mode == 'single':
                    self.close_connection()

                self.robot_is_busy = False
                return -1

            if receive_string.find(b'\x0d\x0a\x3e') >= 0:  # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self.server.recv(4096)
                self.add_to_log("PC program run " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                print(f"{bcolors.WARNING}" + "PC " + program_name + " run" + f"{bcolors.ENDC}")

                if self.connection_mode == 'single':
                    self.close_connection()

                self.robot_is_busy = False
                return 1

            if self.abort_operation:
                self.abort_connection()
                return -1000

    def kill_pc(self, program_name=None, threads=None):
        # type(list) - [None, 'killed', 'not_killed', None, None]
        # None - Don't know about this process
        # 'killed' - PC program killed success
        # 'not_running' - PC program not running
        #
        # -1 - illegal input parameters
        # -1000 - communication error

        if (program_name is not None) and (threads is not None):
            print(f"{bcolors.FAIL}Error:{bcolors.ENDC}")
            print("Kill program by name and by thread number doesn't support")
            return -1

        kill_num = []
        if program_name is None:
            if threads is None:  # Check all threads
                kill_num = [1, 2, 3, 4, 5]
            elif type(threads) == int:
                kill_num = [threads]
            elif type(threads) == list:
                for element in threads:
                    if type(element) == int:
                        if (element <= 5) and (element > 0):
                            if element in kill_num:
                                print("The num. of thread is duplicating")
                                self.abort_connection()
                                self.robot_is_busy = False
                                return -1
                            kill_num.append(element)
                        else:
                            print("Num of thread", element, "out of range: 1-5")
                            self.abort_connection()
                            self.robot_is_busy = False
                            return -1
                    else:
                        print("Num of thread should be int")
                        self.abort_connection()
                        self.robot_is_busy = False
                        return -1
            else:
                print("Threads type is illegal")
                self.abort_connection()
                self.robot_is_busy = False
                return -1
        else:
            pc_status = self.status_pc()
            for i in range(len(pc_status)):
                process = pc_status[i]
                if process['program_name'] == program_name:
                    kill_num.append(i+1)

        if not kill_num:
            print(f"{bcolors.FAIL}" + "PC program " + program_name + " not found" + f"{bcolors.ENDC}")
            return -1

        self.robot_is_busy = True

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        if self._handshake() < 0:
            return -1000

        # receive_string = self.server.recv(4096)  # CLEAN ALL DATA IN BUFFER
        pc_kill_list = [None] * 5

        for thread in kill_num:
            # PCKILL
            self.server.sendall(b'PCKILL ' + bytes(str(thread), "UTF-8") + b':')
            self.server.sendall(b'\x0a')

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)

                # print("RCV", receive_string.decode("utf-8", 'ignore'), receive_string.hex())

                if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    result_msg = receive_string
                    break

                if receive_string.find(b'\x30\x29\x20') >= 0:  # Are you sure ? (Yes:1, No:0)?
                    receive_string = self.server.recv(4096)
                    tmp = bytes.fromhex('31 0a')  # Delete program and abort
                    self.server.sendall(tmp)
                    continue

                if error_counter > error_counter_limit:
                    print("PCKILL CTE")
                    self.add_to_log("PCKILL CTE")
                    self.abort_connection()
                    return -1000

                if self.abort_operation:
                    self.abort_connection()
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
            print(f"{bcolors.FAIL}Can't run program in not REPEAT mode{bcolors.ENDC}")
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

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        if self._handshake() < 0:
            return -1000

        # ZPOW ON
        self.server.sendall(b'ZPOW ON')
        self.server.sendall(b'\x0a')

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x0d\x0a\x3e') >= 0:  # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self.server.recv(4096)
                self.add_to_log("ZPOW ON " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                break

            if error_counter > error_counter_limit:
                self.add_to_log("ZPOW ON CTE")
                print("Execute - ZPOW ON error")
                self.abort_connection()
                return -1000

            if self.abort_operation:
                self.abort_connection()
                return -1000

        # EXECUTE program
        self.server.sendall(b'EXECUTE ' + program_name.encode())
        self.server.sendall(b'\x0a')

        input_buffer = b''
        while True:
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            # print(receive_string.decode("utf-8", 'ignore'), receive_string.hex())
            if receive_string.find(b'Program does not exist.') >= 0:
                receive_string = self.server.recv(4096)
                self.add_to_log("Program does not exist " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                print(f"{bcolors.FAIL}" + "Program " + program_name + " does not exist" + f"{bcolors.ENDC}")

                if self.connection_mode == 'single':
                    self.close_connection()

                self.robot_is_busy = False
                return -1

            if receive_string.find(b'(P1002)Cannot execute program because teach lock is ON.') > -1:
                receive_string = self.server.recv(4096)
                self.add_to_log("Pendant in teach mode " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                print(f"{bcolors.FAIL}Pendant in teach mode{bcolors.ENDC}")

                if self.connection_mode == 'single':
                    self.close_connection()

                self.robot_is_busy = False
                return -1

            if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                tmp_buffer = self.server.recv(4096)
                input_buffer += tmp_buffer

                self.add_to_log("RCP program run " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                print(f"{bcolors.WARNING}" + "RCP " + program_name + " run" + f"{bcolors.ENDC}")

                if not wait_complete:
                    if self.connection_mode == 'single':
                        self.close_connection()

                    self.robot_is_busy = False
                    return 1

            if (input_buffer + receive_string).find(b'Program completed.No = 1') > -1:
                tmp_buffer = self.server.recv(4096)
                input_buffer += tmp_buffer

                self.add_to_log("RCP program completed " + receive_string.decode("utf-8", 'ignore') + ":" + input_buffer.hex())
                print(f"{bcolors.WARNING}" + "RCP " + program_name + " completed" + f"{bcolors.ENDC}")

                if self.connection_mode == 'single':
                    self.close_connection()

                self.robot_is_busy = False
                return 2

            # if self.abort_operation:
            #     self.abort_connection()
            #     print("ABORT MSG")
            #     return -1000

    def status_rcp(self):
        self.robot_is_busy = True

        self.add_cmd_to_buffer(b'STATUS')
        self.add_cmd_to_buffer(footer_message)

        result_msg = self.read_recv([b'\x0d\x0a\x3e'])
        if result_msg is not None:
            if len(result_msg) > 10:
                result_msg = result_msg.decode("utf-8", 'ignore')

            # # self.server.sendall(b'STATUS')
            # # self.server.sendall(footer_message)
            #
                # result_msg = self.wait_recv([b'\x0a\x3e'], timeout=1).decode("utf-8", 'ignore')
                status = {}
                response_list = result_msg.split('\r\n')

                for response_line in response_list:
                    if response_line.find(' mode') >= 0:
                        status.update({"mode": response_line.split(' ')[0]})

                    if response_line.find('Stepper status:') >= 0:
                        status.update({"program_status": ' '.join(response_line.split(' ')[2:]).strip()[:-1]})

                # print("AAA", response_list[-2].find('No program is running.'), result_msg)
                if response_list[-2].find('No program is running.') >= 0:
                    status.update({"program_name": None})
                    status.update({"step_num": None})
                # else:
                #     status.update({"program_name": ''.join(response_list[-2].split(' ')[1].strip())})
                #     status.update({"step_num": response_list[-2].split()[2]})

                self.robot_is_busy = False
                # print(status)

                print(status)
                return status

    def robot_state(self):
        state = {}

        self.add_cmd_to_buffer(b'SWITCH POWER')
        self.add_cmd_to_buffer(footer_message)
        switch_power_str = self.wait_recv([b'\x3e'], timeout=1).decode("utf-8", 'ignore')
        print("WR", switch_power_str)
        state.update({"motor_power": switch_power_str.split()[-2]})

        self.add_cmd_to_buffer(b'SWITCH CS')
        self.add_cmd_to_buffer(footer_message)
        cs_str = self.wait_recv([b'\x3e'], timeout=1).decode("utf-8", 'ignore')
        state.update({"cycle_start": cs_str.split()[-2]})

        self.add_cmd_to_buffer(b'SWITCH RGSO')
        self.add_cmd_to_buffer(footer_message)
        rgso_str = self.wait_recv([b'\x3e'], timeout=1).decode("utf-8", 'ignore')
        state.update({"rgso": cs_str.split()[-2]})

        self.add_cmd_to_buffer(b'SWITCH ERROR')
        self.add_cmd_to_buffer(footer_message)
        error_str = self.wait_recv([b'\x3e'], timeout=1).decode("utf-8", 'ignore')
        if error_str.split()[-2] == "ON":
            self.add_cmd_to_buffer(b'type $ERROR(ERROR)')
            self.add_cmd_to_buffer(footer_message)
            error_text_str = self.wait_recv([b'\x3e'], timeout=1).decode("utf-8", 'ignore')
            state.update({"error": ' '.join(error_text_str.split('\r\n')[1:-1])})
        else:
            state.update({"error": "-"})

        self.add_cmd_to_buffer(b'SWITCH REPEAT')
        self.add_cmd_to_buffer(footer_message)
        repeat_str = self.wait_recv([b'\x3e'], timeout=1).decode("utf-8", 'ignore')
        state.update({"repeat": repeat_str.split()[-2]})

        self.add_cmd_to_buffer(b'SWITCH RUN')
        self.add_cmd_to_buffer(footer_message)
        run_str = self.wait_recv([b'\x3e'], timeout=1).decode("utf-8", 'ignore')
        state.update({"run": repeat_str.split()[-2]})

        return state

    def abort_rcp(self, standalone=True):
        if standalone:
            self.robot_is_busy = True

        self.server.sendall("ABORT".encode())
        self.server.sendall(footer_message)

        kawasaki_msg = self.wait_recv([b'ABORT' + b'\x0d\x0a\x3e'], timeout=1)

        if standalone:
            self.robot_is_busy = False

        return 1

    def kill_rcp(self, standalone=True):
        if standalone:
            self.robot_is_busy = True

        self.server.sendall("KILL".encode())
        self.server.sendall(footer_message)

        kawasaki_msg = self.wait_recv([b'\x3a\x30\x29\x20'], timeout=1)  # END (Yes:1, No:0)

        self.server.sendall(b'\x31\x0a')  # Delete program and abort

        kawasaki_msg = self.wait_recv([b'\x31\x0d\x0a\x3e'], timeout=1)

        if standalone:
            self.robot_is_busy = False

        return 1

    def read_variable_real(self, variable_name):
        # -1000 - connection error
        # -1 - any error

        self.robot_is_busy = True

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        self.server.sendall(b'list /r ' + bytes(str(variable_name), 'utf-8'))
        self.server.sendall(b'\x0a')

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x0d\x0a\x3e') > -1:
                tmp_string = self.server.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("Read variable CTE")
                self.add_to_log("Read variable CTE")
                self.abort_connection()
                return -1000

            if self.abort_operation:
                self.abort_connection()
                return -1000

        real_variable = float(tmp_string.split()[-2])
        return real_variable

    def read_programs_list(self):
        self.server.sendall("DIRECTORY/P".encode())
        self.server.sendall(footer_message)

        kawasaki_msg = self.wait_recv([b'\x3e'], timeout=1)
        kawasaki_msg = kawasaki_msg.decode("utf-8", 'ignore')

        response_strings = kawasaki_msg.split('\r\n')
        if len(response_strings) > 3:
            pg_list_str = response_strings[2]
            pg_list = [item.strip() for item in pg_list_str.split() if item.strip() != ""]
            return pg_list

    def _handshake(self):
        # 1 - without errors
        # -1000 - connection errors and abort

        self.server.sendall(b'\x0a')
        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)

            if receive_string.find(b'\x0d\x0a\x3e') > -1:
                receive_string = self.server.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("Handshake error")
                self.abort_connection()
                return -1000

            if self.abort_operation:
                self.abort_connection()
                return -1000
        return 1

    def add_to_log(self, msg):
        if self.logging:
            self.logfile.write(str(time.time()) + ":" + msg + '\n')
