import socket
import time
import math
import re


error_counter_limit = 100000


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
    def __init__(self, ip, port, connection_mode='single', log=False):
        self.ip_address = ip
        self.port_number = port
        self.logging = log

        if self.logging:
            self.logfile = open("log.txt", "w")
            self.logfile.write(str(time.time()) + ":" + "Log started" + '\n')

        self.server = None

        if connection_mode == 'continuous':
            if self.connect() == -1:
                print(f"{bcolors.WARNING}Can't establish connection with robot."
                      f" Continue in single connection mode{bcolors.ENDC}")
                self.connection_mode = 'single'
                self.add_to_log("Can't connect to robot continuously, set single mode")
            else:
                self.connection_mode = 'continuous'
                self.add_to_log("Connection mode - continuous")

        elif connection_mode == 'single':
            self.connection_mode = 'single'
            self.add_to_log("Connection mode - single")

        else:
            print(f"{bcolors.WARNING}Can't find this connection mode."
                  f" Continue in single connection mode{bcolors.ENDC}")
            self.connection_mode = 'single'

        self.robot_is_busy = False
        self.abort_operation = False

    def connect(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.connect((self.ip_address, self.port_number))

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'login:') >= 0:     # Wait 'login:' message from robot
                receive_string = self.server.recv(4096)
                self.add_to_log("Robot->PC 1 " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                break
            if error_counter > error_counter_limit:
                self.add_to_log("Robot->PC CTE 1" + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                print("Connection timeout error - 1")
                self.server.close()
                return -1

        self.server.sendall(b'as')
        self.server.sendall(b'\x0d\x0a')

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x3e') >= 0:     # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self.server.recv(4096)
                self.add_to_log("Robot->PC 2 " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                return 0
            if error_counter > error_counter_limit:
                self.add_to_log("Robot->PC CTE 2" + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                print("Connection timeout error - 2")
                self.server.close()
                return -1

    def ereset(self):
        #  Return:
        # 1 - everything is ok
        # -1000 - communication with robot was aborted

        self.robot_is_busy = True

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        # handshake
        self.server.sendall(b'\x0a')
        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x0d\x0a\x3e') >= 0:  # 'Cleared error state'
                receive_string = self.server.recv(4096)
                break
            if error_counter > error_counter_limit:
                print("ERESET - handshake error")
                self.abort_connection()
                self.robot_is_busy = False
                return -1000

            if self.abort_operation:
                if self.connection_mode == 'single':
                    self.abort_connection()
                self.robot_is_busy = False
                self.abort_operation = False
                return -1000

        # ERESET
        self.server.sendall(b'ERESET')
        self.server.sendall(b'\x0a')

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'state' + b'\x2e\x0d\x0a\x3e') >= 0:  # 'Cleared error state'
                receive_string = self.server.recv(4096)
                break
            if receive_string.find(b'ERESET' + b'\x0d\x0a\x3e') >= 0:  # 'ERESET' (without clear = not error)
                receive_string = self.server.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("ERESET timeout error")
                self.abort_connection()
                self.robot_is_busy = False
                return -1000

            if self.abort_operation:
                if self.connection_mode == 'single':
                    self.abort_connection()
                self.robot_is_busy = False
                self.abort_operation = False
                return -1000

    def close_connection(self):
        self.add_to_log("Close connection")
        self.server.close()

    def abort_connection(self):
        if self.connection_mode == 'continuous':
            self.connection_mode = 'single'
            self.add_to_log("Abort connection")
        self.server.close()

    def upload_program(self, filename=None, program_name=None, program_text=None, kill_current_program=True):
        #  Return:
        #  None - everything is OK
        # -1 -upload with error
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

        self.robot_is_busy = True

        footer_message = bytes.fromhex('0a')

        # Read file data and split to packages
        # one package limit is 2918 byte (in KIDE)
        if filename is not None:
            f = open(filename, "r")
            file_string = f.read()
        else:
            file_string = '.PROGRAM ' + program_name + '\n'
            file_string += program_text + '\n'
            file_string += '.END' + '\n'

        file = bytes(file_string, 'utf-8') + bytes.fromhex('0d 0a')
        num_packages = math.ceil(len(file) / 2910)
        file_packages = []

        for i in range(num_packages):
            pckg = bytes.fromhex('02 43 20 20 20 20 30') + \
                   file[i * 2910:(i + 1) * 2910] + \
                   bytes.fromhex('17')
            file_packages.append(pckg)

        if self.connection_mode == 'single':
            # Connect to robot in single mode
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        if kill_current_program:
            # Hold robot
            self.server.sendall("HOLD".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'HOLD' + b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    self.add_to_log("HOLD " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("HOLD CTE")
                    self.abort_connection()
                    return -1000

            # ZPOW OFF robot
            self.server.sendall("ZPOW OFF".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'ZPOW OFF' + b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    self.add_to_log("ZPOW OFF " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("ZPOW OFF CTE")
                    self.abort_connection()
                    return -1000

            # ABORT robot
            self.server.sendall("ABORT".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'ABORT' + b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    self.add_to_log("ABORT " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("ABORT CTE")
                    self.abort_connection()
                    return -1000

            # KILL robot
            self.server.sendall("KILL".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'\x3a\x30\x29\x20') >= 0:  # END (Yes:1, No:0)
                    receive_string = self.server.recv(4096)
                    self.add_to_log("KILL " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("KILL CTE 1")
                    self.abort_connection()
                    return -1000

            tmp = bytes.fromhex('31 0a')  # Delete program and abort
            self.server.sendall(tmp)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'\x31\x0d\x0a\x3e') >= 0:
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("KILL CTE 2")
                    self.abort_connection()
                    return -1000

            # TYPE TASK (1) robot
            self.server.sendall("TYPE TASK (1)".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'\x30\x0d\x0a\x3e') >= 0:
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("TYPE TASK CTE")
                    self.abort_connection()
                    return -1000

            self.server.sendall(footer_message)
            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                    break

                if error_counter > error_counter_limit:
                    self.abort_connection()
                    return -1000

        # Enable loading mode
        self.server.sendall("LOAD using.rcc".encode())
        self.server.sendall(footer_message)

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            # print("0", receive_string.decode("utf-8", 'ignore'), receive_string.hex())
            if receive_string.find(b'Ausing.rcc' + b'\x17') >= 0:
                input_buffer = self.server.recv(4096)
                segment_pos = input_buffer.find(b'Ausing.rcc' + b'\x17')
                input_buffer = input_buffer[segment_pos + len(b'Ausing.rcc' + b'\x17'):]
                self.add_to_log("LOAD using.rcc " + input_buffer.decode("utf-8", 'ignore') + ":" + input_buffer.hex())
                break

            if error_counter > error_counter_limit:
                self.add_to_log("LOAD using.rcc CTE")
                self.abort_connection()
                return -1000

        tmp = bytes.fromhex('02 41 20 20 20 20 30 17')
        self.server.sendall(tmp)

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            # print("0.5", receive_string.decode("utf-8", 'ignore'), receive_string.hex())
            if receive_string.find(b'(using.rcc)' + b'\x0d\x0a') >= 0:
                input_buffer = input_buffer + self.server.recv(4096)
                segment_pos = input_buffer.find(b'(using.rcc)' + b'\x0d\x0a')
                input_buffer = input_buffer[segment_pos + len(b'(using.rcc)' + b'\x0d\x0a'):]
                self.add_to_log("LOAD 1 " + input_buffer.decode("utf-8", 'ignore') + ":" + input_buffer.hex())
                break

            if error_counter > error_counter_limit:
                self.add_to_log("LOAD 1 CTE")
                self.abort_connection()
                return -1000

        # File transmission
        i = 0
        upload_success = True
        for byte_package in file_packages:
            if upload_success:
                self.server.sendall(byte_package)

                error_counter = 0
                while True:
                    error_counter += 1
                    receive_string = self.server.recv(4096, socket.MSG_PEEK)
                    # print("F", i, receive_string.decode("utf-8", 'ignore'), receive_string.hex())
                    if receive_string.find(b'\x05\x02\x43\x17') >= 0:
                        tmp_buffer = self.server.recv(4096)
                        segment_pos = tmp_buffer.find(b'\x05\x02\x43\x17')

                        input_buffer = input_buffer + \
                                       tmp_buffer[:segment_pos] + \
                                       tmp_buffer[segment_pos + len(b'\x05\x02\x43\x17'):]
                        self.add_to_log("uploading " + str(i) + ":" + tmp_buffer.decode("utf-8", 'ignore') + ":" + tmp_buffer.hex())
                        i += 1
                        break

                    if receive_string.find(b'\x72\x74\x29\x0d\x0a') >= 0:    # End of 'abort)'
                        input_buffer = input_buffer + self.server.recv(4096)
                        upload_success = False
                        break

                    if error_counter > error_counter_limit:
                        self.add_to_log("uploading CTE")
                        self.abort_connection()
                        return -1000
            else:
                break

        if upload_success:
            tmp = bytes.fromhex('02 43 20 20 20 20 30 1a 17')  # 9
            self.server.sendall(tmp)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                # print("3", receive_string.decode("utf-8", 'ignore'), receive_string.hex())
                if receive_string.find(b'\x05\x02\x45\x17') >= 0:
                    tmp_buffer = self.server.recv(4096)
                    segment_pos = tmp_buffer.find(b'\x05\x02\x45\x17')

                    input_buffer = input_buffer + \
                                   tmp_buffer[:segment_pos] + \
                                   tmp_buffer[segment_pos + len(b'\x05\x02\x45\x17'):]
                    break
                if receive_string.find(b'\x72\x74\x29\x0d\x0a') >= 0:  # End of 'abort)'
                    input_buffer = input_buffer + self.server.recv(4096)
                    upload_success = False
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("Error 3 CTE")
                    self.abort_connection()
                    return -1000

        self.add_to_log("Upload success " + str(upload_success))

        continue_removing_packages = True
        if not upload_success:
            while continue_removing_packages:
                tmp = bytes.fromhex('02 43 20 20 20 20 30 1a 17')  # Abort loading
                self.server.sendall(tmp)
                tmp = bytes.fromhex('30 0a')  # Delete program and abort
                self.server.sendall(tmp)

                error_counter = 0
                while True:
                    error_counter += 1
                    receive_string = self.server.recv(4096, socket.MSG_PEEK)
                    # print("SC", receive_string.decode("utf-8", 'ignore'), receive_string.hex())
                    if receive_string.find(b'\x05\x02\x45\x17') >= 0:
                        receive_string = self.server.recv(4096)
                        continue_removing_packages = False
                        break
                    if receive_string.find(b'\x20\x21\x0d\x0a') >= 0:  # Program * loaded in error and deleted. Confirm !
                        receive_string = self.server.recv(4096)
                        self.server.sendall(footer_message)
                        continue_removing_packages = False
                        break
                    if receive_string.find(b'\x72\x74\x29\x0d\x0a') >= 0:  # End of 'abort)'
                        input_buffer += self.server.recv(4096)
                        self.server.sendall(footer_message)
                        break

                    if error_counter > error_counter_limit:
                        self.add_to_log("Error 4 CTE")
                        self.abort_connection()
                        return -1000

        error_message = input_buffer.decode("utf-8", 'ignore')

        tmp = bytes.fromhex('02 45 20 20 20 20 30 17')  # Cancel loading mode
        self.server.sendall(tmp)

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            # print("SCF", receive_string.decode("utf-8", 'ignore'), receive_string.hex())
            if receive_string.find(b'\x29\x0d\x0a\x3e') >= 0:  # waiting 'File load completed. (n errors)' + 0d 0a 3e.
                receive_string = self.server.recv(4096)
                self.add_to_log("Loading complete " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                split_message = receive_string.decode("utf-8", 'ignore').split(" ")
                break

            if error_counter > error_counter_limit:
                self.add_to_log("Error 5 CTE")
                self.abort_connection()
                return -1000

        if len(split_message) > 2:
            num_errors = int(split_message[-2][1:])

        if num_errors == 0:
            print("File transmission complete")

            if self.connection_mode == 'single':
                self.abort_connection()
            self.robot_is_busy = False

            return None
        else:
            print(f"{bcolors.FAIL}File transmission not complete - Errors found{bcolors.ENDC}")
            print("Errors list:")
            print(error_message)
            print("Num errors:", num_errors)
            print("-----------------")

            if self.connection_mode == 'single':
                self.abort_connection()
            self.robot_is_busy = False

            return -1

    def upload_program_experimental(self, filename=None, program_name=None, program_text=None, kill_current_program=True):
        #  Return:
        #  None - everything is OK
        # -1 -upload with error
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

        # pc_status = self.status_pc()
        # for i in range(len(pc_status)):
        #     process = pc_status[i]
        #     if process['PCNAME'] == program_name:
        #         abort_num.append(i + 1)

        self.robot_is_busy = True

        footer_message = bytes.fromhex('0a')

        # Read file data and split to packages
        # one package limit is 2918 byte (in KIDE)
        if filename is not None:
            f = open(filename, "r")
            first_line = f.readline()
            file_string = first_line + f.read()

            program_name = first_line.split(' ')[1].split('(')[0]
            abort_prog = self.abort_pc(program_name=program_name)
            kill_prog = self.kill_pc(program_name=program_name)
        else:
            file_string = '.PROGRAM ' + program_name + '\n'
            file_string += program_text + '\n'
            file_string += '.END' + '\n'

        file = bytes(file_string, 'utf-8') + bytes.fromhex('0d 0a')
        num_packages = math.ceil(len(file) / 2910)
        file_packages = []

        for i in range(num_packages):
            pckg = bytes.fromhex('02 43 20 20 20 20 30') + \
                   file[i * 2910:(i + 1) * 2910] + \
                   bytes.fromhex('17')
            file_packages.append(pckg)

        if self.connection_mode == 'single':
            # Connect to robot in single mode
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        if kill_current_program:
            # Hold robot
            self.server.sendall("HOLD".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'HOLD' + b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    self.add_to_log("HOLD " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("HOLD CTE")
                    self.abort_connection()
                    return -1000

            # ZPOW OFF robot
            self.server.sendall("ZPOW OFF".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'ZPOW OFF' + b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    self.add_to_log("ZPOW OFF " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("ZPOW OFF CTE")
                    self.abort_connection()
                    return -1000

            # ABORT robot
            self.server.sendall("ABORT".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'ABORT' + b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    self.add_to_log("ABORT " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("ABORT CTE")
                    self.abort_connection()
                    return -1000

            # KILL robot
            self.server.sendall("KILL".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'\x3a\x30\x29\x20') >= 0:  # END (Yes:1, No:0)
                    receive_string = self.server.recv(4096)
                    self.add_to_log("KILL " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("KILL CTE 1")
                    self.abort_connection()
                    return -1000

            tmp = bytes.fromhex('31 0a')  # Delete program and abort
            self.server.sendall(tmp)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'\x31\x0d\x0a\x3e') >= 0:
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("KILL CTE 2")
                    self.abort_connection()
                    return -1000

            # TYPE TASK (1) robot
            self.server.sendall("TYPE TASK (1)".encode())
            self.server.sendall(footer_message)

            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'\x30\x0d\x0a\x3e') >= 0:
                    break

                if error_counter > error_counter_limit:
                    self.add_to_log("TYPE TASK CTE")
                    self.abort_connection()
                    return -1000

            self.server.sendall(footer_message)
            error_counter = 0
            while True:
                error_counter += 1
                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                    receive_string = self.server.recv(4096)
                    break

                if error_counter > error_counter_limit:
                    self.abort_connection()
                    return -1000

        # Enable loading mode
        self.server.sendall("LOAD using.rcc".encode())
        self.server.sendall(footer_message)

        tmp = bytes.fromhex('02 41 20 20 20 20 30 17')
        self.server.sendall(tmp)

        while True:
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'Loading...(using.rcc)' + b'\x0d\x0a') >= 0:  # package receive
                tmp_buffer = self.server.recv(4096)
                break

            if receive_string.find(b'\x65\x73\x73\x2e\x0d\x0a\x3e') >= 0:  # End of 'SAVE/LOAD in progress.'
                tmp_buffer = self.server.recv(4096)
                self.add_to_log("SAVE/LOAD in progress.")
                print("SAVE/LOAD in progress.")

                if self.connection_mode == 'single':
                    self.abort_connection()

                return -1

        # File transmission
        input_buffer = b''
        i = 0
        error_not_found = True
        for byte_package in file_packages:
            if error_not_found:
                self.server.sendall(byte_package)
                while True:
                    receive_string = self.server.recv(4096, socket.MSG_PEEK)

                    if receive_string.find(b'\x05\x02\x43\x17') >= 0:  # package receive
                        tmp_buffer = self.server.recv(4096)
                        break

                    if receive_string.find(b'\x72\x74\x29\x0d\x0a') >= 0:  # End of 'abort)'
                        tmp_buffer = self.server.recv(4096)
                        self.add_to_log("Error in program found")
                        input_buffer += tmp_buffer
                        self.server.sendall(b'\x31\x0a')  # 31 - discard program and delete
                        continue

                    if receive_string.find(b'\x05\x02\x45\x17') >= 0:  # abort transmission
                        tmp_buffer = self.server.recv(4096)
                        error_not_found = False
                        break

        tmp = bytes.fromhex('02 43 20 20 20 20 30 1a 17')  # 9
        self.server.sendall(tmp)

        tmp = bytes.fromhex('02 45 20 20 20 20 30 17')  # Cancel loading mode
        self.server.sendall(tmp)

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            self.add_to_log("RCV " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())

            if receive_string.find(b'\x72\x74\x29\x0d\x0a') >= 0:  # End of 'abort)'
                tmp_buffer = self.server.recv(4096)
                self.add_to_log("Delete program and abort")
                input_buffer += tmp_buffer
                self.server.sendall(b'\x30\x0a')
                continue

            if receive_string.find(b'\x73\x29\x0d\x0a\x3e') >= 0:  # End of 'errors)'
                tmp_buffer = self.server.recv(4096)
                self.add_to_log("File load completed. (n errors)")
                input_buffer += tmp_buffer
                break

        split_message = input_buffer.decode("utf-8", 'ignore').split(" ")

        if len(split_message) > 2:
            num_errors = int(split_message[-2][1:])

        if num_errors == 0:
            print("File transmission complete")

            if self.connection_mode == 'single':
                self.abort_connection()
            self.robot_is_busy = False

            return None
        else:
            print(f"{bcolors.FAIL}File transmission not complete - Errors found{bcolors.ENDC}")
            print("Errors list:")
            print(input_buffer.decode("utf-8", 'ignore'))
            print("Num errors:", num_errors)
            print("-----------------")

        if self.connection_mode == 'single':
            self.abort_connection()

        self.robot_is_busy = False

        return -1

    def status_pc(self, threads=None):

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
                    self.robot_is_busy = False
                    return -1000

            list_of_strings = result_msg.split('\r\n')

            list_thread_status = list_of_strings[1][:-1].split()
            pc_status = ' '.join(list_thread_status[2:])
            if pc_status == 'Program running':
                pc_status = True
            else:
                pc_status = False

            list_thread_name = list_of_strings[6].split()
            if list_thread_name[0] == 'No':
                pc_name = None
            else:
                pc_name = list_thread_name[0]

            if (pc_name is not None) and (pc_status == False):
                pc_aborted = True
            else:
                pc_aborted = False

            # print("Result msg:", list_of_strings)

            thread_dict = {"PCRUNNING": pc_status,
                           "PCNAME": pc_name,
                           "PCABORTED": pc_aborted}

            pc_status_list[thread-1] = thread_dict

        if self.connection_mode == 'single':
            self.abort_connection()

        return pc_status_list

        self.robot_is_busy = False

    def abort_pc(self, program_name=None, threads=None):
        # type(list) - [None, 'aborted', 'not_running', None, 'not_running']
        # None - if don't know about this process
        # 'aborted' - PC program aborted success
        # 'not_running' - PC program not running
        #
        # -1 - illegal input parameters
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
                abort_num = [threads]
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
        else:  # Program name is not none
            pc_status = self.status_pc()
            for i in range(len(pc_status)):
                process = pc_status[i]
                if process['PCNAME'] == program_name:
                    abort_num.append(i+1)

        if not abort_num:
            print("PC program not found")
            return -1

        self.robot_is_busy = True

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        # handshake
        self.server.sendall(b'\x0a')
        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                receive_string = self.server.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("PCABORT - handshake error")
                self.add_to_log("PCABORT handshake CTE")
                self.abort_connection()
                self.robot_is_busy = False
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
                    self.robot_is_busy = False
                    return -1000

            if result_msg.find('PC program aborted.No') >= 0:
                pc_abort_list[thread-1] = 'aborted'
            else:
                pc_abort_list[thread - 1] = 'not_running'

        return pc_abort_list

    def execute_pc_program(self, program_name, thread):
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

        status = self.status_pc()

        kill_list = []

        for i in range(len(status)):
            thread_status = status[i]
            if thread_status['PCNAME'] == program_name:
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

        # handshake
        self.server.sendall(b'\x0a')
        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                receive_string = self.server.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("PCEXECUTE - handshake error")
                self.add_to_log("Execute handshake CTE")
                self.abort_connection()
                self.robot_is_busy = False
                return -1000

        # ERESET
        self.server.sendall(b'ERESET')
        self.server.sendall(b'\x0a')

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'state' + b'\x2e\x0d\x0a\x3e') >= 0:  # 'Cleared error state'
                receive_string = self.server.recv(4096)
                self.add_to_log("ERESET 1 " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                break
            if receive_string.find(b'ERESET' + b'\x0d\x0a\x3e') >= 0:  # 'ERESET' (without clear = not error)
                receive_string = self.server.recv(4096)
                self.add_to_log("ERESET 2 " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                break

            if error_counter > error_counter_limit:
                self.add_to_log("Execute ERESET CTE")
                print("Execute - ERESET error")
                self.abort_connection()
                self.robot_is_busy = False
                return -1000

        # EXECUTE program
        self.server.sendall(b'PCEXECUTE ' + bytes(str(thread), 'utf-8') + b':' + program_name.encode())
        self.server.sendall(b'\x0a')

        while True:
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            # print(receive_string.decode("utf-8", 'ignore'), receive_string.hex())
            if receive_string.find(b'\x0d\x0a\x3e') >= 0:  # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self.server.recv(4096)
                self.add_to_log("PC program run " + receive_string.decode("utf-8", 'ignore') + ":" + receive_string.hex())
                print(f"{bcolors.WARNING}PC program run{bcolors.ENDC}")

                if self.connection_mode == 'single':
                    self.abort_connection()

                self.robot_is_busy = False
                return 1

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
                if process['PCNAME'] == program_name:
                    kill_num.append(i+1)

        self.robot_is_busy = True

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        # handshake
        self.server.sendall(b'\x0a')
        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x0d\x0a\x3e') >= 0:
                receive_string = self.server.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("PCKILL - handshake error")
                self.add_to_log("PCKILL handshake CTE")
                self.abort_connection()
                self.robot_is_busy = False
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
                    self.robot_is_busy = False
                    return -1000

            if result_msg.find(b'Cannot KILL program that is running.') >= 0:
                pc_kill_list[thread - 1] = 'not_killed'
            elif result_msg.find(b'\x31\x0d\x0a\x3e') >= 0:
                pc_kill_list[thread - 1] = 'killed'
            else:
                pc_kill_list[thread - 1] = 'unknown'

        return pc_kill_list

    def add_to_log(self, msg):
        if self.logging:
            self.logfile.write(str(time.time()) + ":" + msg + '\n')
