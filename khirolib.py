import socket
import time
import math


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
    def __init__(self, ip, port, connection_mode='single'):
        self.ip_address = ip
        self.port_number = port

        self.server = None

        if connection_mode == 'continuous':
            if self.connect() == -1:
                print(f"{bcolors.WARNING}Can't establish connection with robot."
                      f" Continue in single connection mode{bcolors.ENDC}")
                self.connection_mode = 'single'
            else:
                self.connection_mode = 'continuous'

        elif connection_mode == 'single':
            self.connection_mode = 'single'

        else:
            print(f"{bcolors.WARNING}Can't find this connection mode."
                  f" Continue in single connection mode{bcolors.ENDC}")
            self.connection_mode = 'single'

        self.robot_is_busy = False
        self.abort_operation = False

    def upload_variables(self, variables_text):
        # !!! Still in BETA - doesn't work
        # Return
        # 1 - everything is ok
        # -1 - not all variables uploaded correct
        # -1000 - communication error

        self.robot_is_busy = True
        self.abort_operation = False

        footer_message = bytes.fromhex('0a')
        empty_message = bytes.fromhex('')

        if self.connection_mode == 'single':
            if self.connect() == -1:
                print("Can't establish connection with robot")
                return -1000

        list_of_strings = variables_text.split('\n')
        list_of_strings = [i for i in list_of_strings if i]  # Delete empty elements from string (\n in the end problem)
        num_variables = len(list_of_strings)

        time_start = time.time_ns()

        for line in list_of_strings:
            message = bytes(line, 'utf-8')
            self.server.sendall(message)
            self.server.sendall(footer_message)

            counter = 0
            while True:
                if self.abort_operation:
                    self.abort_connection()
                    self.robot_is_busy = False
                    return -1000

                receive_string = self.server.recv(4096, socket.MSG_PEEK)
                if receive_string[-1] == 62:  # 62 is equal 3e (>) - end of robot answer
                    self.server.sendall(empty_message)
                    break

                if counter > 100:
                    print("Transmission timeout is over")
                    self.abort_connection()
                    self.robot_is_busy = False
                    return -1000
                else:
                    counter += 1

            time.sleep(0.001)

        # self.server.sendall(footer_message)
        # time.sleep(0.1)

        if self.connection_mode == 'single':
            self.close_connection()

        self.robot_is_busy = False

        time_complete = time.time_ns()

        print("Variable transmission complete, time in ms:", int((time_complete-time_start)/1000000))

        return 1

    def execute_program(self, program_name):
        #  Return:
        # 1 - everything is ok
        # 2 - XAC error detected (touch sensing error in welding robot)
        # 3 - program HALT error detected
        # 4 - program aborted
        # -1000 - communication with robot was aborted

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
            if receive_string.find(b'\x0d\x0a\x3e') >= 0:  # 'Cleared error state'
                receive_string = self.server.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("Execute - handshake error")
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
                break
            if receive_string.find(b'ERESET' + b'\x0d\x0a\x3e') >= 0:  # 'ERESET' (without clear = not error)
                receive_string = self.server.recv(4096)
                break

            if error_counter > error_counter_limit:
                print("Execute - ERESET error")
                self.abort_connection()
                self.robot_is_busy = False
                return -1000

        # ZPOW ON
        self.server.sendall(b'ZPOW ON')
        self.server.sendall(b'\x0a')

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'\x0d\x0a\x3e') >= 0:     # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self.server.recv(4096)
                break
            if error_counter > error_counter_limit:
                print("Execute - ZPOW ON error")
                self.abort_connection()
                self.robot_is_busy = False
                return -1000

        # EXECUTE program
        self.server.sendall(b'EXECUTE ' + program_name.encode())
        self.server.sendall(b'\x0a')

        while True:
            receive_string = self.server.recv(4096, socket.MSG_PEEK)

            if receive_string.find(b'completed.No = 1') >= 0:  # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self.server.recv(4096)
                print(f"{bcolors.WARNING}Program complete.{bcolors.ENDC}")

                if self.connection_mode == 'single':
                    self.abort_connection()

                self.robot_is_busy = False
                return 1

            if receive_string.find(b'(E6509) No work detected') > 0:
                receive_string = self.server.recv(4096)
                print(f"{bcolors.WARNING}Program not complete. TS error detected.{bcolors.ENDC}")

                if self.connection_mode == 'single':
                    self.abort_connection()

                self.robot_is_busy = False
                return 2

            if receive_string.find(b'Program halted.No = 1') > 0:
                receive_string = self.server.recv(4096)
                print(f"{bcolors.WARNING}Program not complete. Program halted.{bcolors.ENDC}")

                if self.connection_mode == 'single':
                    self.abort_connection()

                self.robot_is_busy = False
                return 3

            if receive_string.find(b'aborted.No = 1') >= 0:  # This is AS monitor terminal..  Wait '>' sign from robot
                receive_string = self.server.recv(4096)
                print("Execution program aborted")

                if self.connection_mode == 'single':
                    self.abort_connection()

                self.robot_is_busy = False
                return 4

            if self.abort_operation:
                if self.connection_mode == 'single':
                    self.abort_connection()

                self.robot_is_busy = False
                self.abort_operation = False
                return -1000

    def connect(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.connect((self.ip_address, self.port_number))

        error_counter = 0
        while True:
            error_counter += 1
            receive_string = self.server.recv(4096, socket.MSG_PEEK)
            if receive_string.find(b'login:') >= 0:     # Wait 'login:' message from robot
                receive_string = self.server.recv(4096)
                break
            if error_counter > error_counter_limit:
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
                return 0
            if error_counter > error_counter_limit:
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
        self.server.close()

    def abort_connection(self):
        if self.connection_mode == 'continuous':
            self.connection_mode = 'single'
        self.server.close()

    def upload_program(self, filename=None, program_name=None, program_text=None, kill_current_program=True):
        #  Return:
        #  None - everything is OK
        # -1 -upload with error
        # -2 - function arguments error
        # -1000 - communication with robot was aborted

        if filename is None:
            if (program_name is None) or (program_text is None):
                print("You should set correct function arguments")
                return -2
        else:
            if (program_name is not None) or (program_text is not None):
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
                    tmp = self.server.recv(4096)
                    break

                if error_counter > error_counter_limit:
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
                    tmp = self.server.recv(4096)
                    break

                if error_counter > error_counter_limit:
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
                    tmp = self.server.recv(4096)
                    break

                if error_counter > error_counter_limit:
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
                    tmp = self.server.recv(4096)
                    break

                if error_counter > error_counter_limit:
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
                break

            if error_counter > error_counter_limit:
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
                break

            if error_counter > error_counter_limit:
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
                        i += 1
                        break

                    if receive_string.find(b'\x72\x74\x29\x0d\x0a') >= 0:    # End of 'abort)'
                        input_buffer = input_buffer + self.server.recv(4096)
                        upload_success = False
                        break

                    if error_counter > error_counter_limit:
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
                    self.abort_connection()
                    return -1000

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
                receive_string = self.server.recv(4096).decode("utf-8", 'ignore')
                split_message = receive_string.split(" ")
                break

            if error_counter > error_counter_limit:
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
            print("File transmission not complete - Errors found")
            print(error_message)
            print("Num errors:", num_errors)

            if self.connection_mode == 'single':
                self.abort_connection()
            self.robot_is_busy = False

            return -1
