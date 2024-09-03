import math
from utils.thread_state import ThreadState
from utils.rcp_state import RCPState
from src.tcp_sock_client import TCPSockClient
from src.khi_exception import *

# One package size in bytes for splitting large programs. Slightly faster at higher values
# It's 2962 bytes in KIDE and robot is responding for up to 3064 bytes
UPLOAD_BATCH_SIZE = 1000


NEWLINE_MSG = b"\x0d\x0a\x3e"                      # "\r\n>" - Message when clearing terminal

""" Service byte sequences for various steps of loading program via telnet connection """
START_LOADING = b"LOAD using.rcc\r\n" + b"\x02\x41\x20\x20\x20\x20\x30\x17"
SAVE_LOAD_ERROR = b"\x65\x73\x73\x2e\x0d\x0a\x3e"                 # Previous save/load operation didn't end
START_UPLOAD_SEQ = b"\x02\x43\x20\x20\x20\x20\x30"                # Suffix for a data batch
END_UPLOAD_SEQ = b"\x17"                                          # Postfix for a data batch
CANCEL_LOADING = b"\x0d\x0a\x1a\x17\x02\x45\x20\x20\x20\x20\x30"  # Message to indicate last data batch
PKG_RECV = b"\x05\x02\x43\x17"                                    # Byte sequence when program batch is accepted
CONFIRM_TRANSMISSION = b"\x73\x29\x0d\x0a\x3e"                    # Message from robot confirming transmission
NAME_CONFIRMATION = b"\x26\x29\x0d\x0a"                           # ()\r\n

""" Status and Error messages """
CONFIRMATION_REQUEST = b'\x30\x29\x20'                            # Are you sure ? (Yes:1, No:0)?
PROGRAM_COMPLETED = b"Program completed.No = 1"
PROGRAM_ABORTED = b"Program aborted.No = 1"
PROGRAM_STOPPED = b"No = 1"                                       # Just finished or stopped
PROGRAM_HELD = b"Program held.No = 1"

SYNTAX_ERROR = b"\r\nSTEP syntax error.\r\n(0:Change to comment and continue, 1:Delete program and abort)\r\n"
VARIABLE_NOT_DEFINED = b"(E0102) Variable is not defined."
TEACH_MODE_ON = b"program in TEACH mode."                         # Running RCP program in teach mode
TEACH_LOCK_ON = b"teach lock is ON."                              # Running RCP program when pendant teach lock is on
PROGRAM_IN_USE = b"program already in use."                       # Program is already running in different thread
PROG_IS_LOADED = b"KILL or PCKILL to delete program."             # Program is halted via pcabort. Use KILL pr PCKILL
THREAD_IS_BUSY = b"PC program is running."                        # Another program is running in this thread
PROG_NOT_EXIST = b"Program does not exist."                       # Program does not exist error
PROG_IS_ACTIVE = b"Cannot KILL program that is running."          # Program is active and can't be killed
MOTORS_DISABLED = b"motor power is OFF."                          # Running RCP program with motors powered OFF
RCP_IS_RUNNING = b"Robot control program is already running."     # Program is running and can't be deleted
ERROR_NOW = b"(P1013)Cannot execute because in error now. Reset error.\r\n>"

# Custom errors
WELDER_ERROR_1 = b"Welder error occurred."                               # Can't do arcon


def telnet_connect(client: TCPSockClient) -> None:
    try:
        client.wait_recv(b"login")              # Send 'as' as login for kawasaki telnet terminal
        client.send_msg("as")                   # Confirm with carriage return and line feed control symbols
        client.wait_recv(NEWLINE_MSG)           # wait for '>' symbol of a kawasaki terminal new line
    except (TimeoutError, ConnectionRefusedError):
        raise KHIConnError()


def handshake(client: TCPSockClient) -> None:
    """ Performs a handshake with the robot and raises an exception if something fails """
    client.send_msg("")                         # Send empty command
    if not client.wait_recv(NEWLINE_MSG):       # Wait for newline symbol
        raise KHIConnError()


def ereset(client: TCPSockClient) -> None:
    client.send_msg("ERESET")
    client.wait_recv(NEWLINE_MSG)


def disconnect(client: TCPSockClient) -> None:
    client.disconnect()


def get_sys_switch(client: TCPSockClient, switch_name: str) -> bool:
    """ Sets robot system switch state """
    client.send_msg("SWITCH " + switch_name)
    return client.wait_recv(NEWLINE_MSG).split()[-2].decode() == "ON"


def set_sys_switch(client: TCPSockClient, switch_name: str, value: bool) -> None:
    """ Sets robot system switch. Note that switch might be read-only,
        in that case switch value won't be changed """
    client.send_msg(switch_name + "ON" if value else "OFF")
    client.wait_recv(NEWLINE_MSG)


def get_error_descr(client: TCPSockClient) -> str:
    """ Returns robot error state description, empty string if no error """
    client.send_msg("type $ERROR(ERROR)")
    res = client.wait_recv(NEWLINE_MSG).decode()
    if "Value is out of range." not in res:
        return ' '.join(res.split('\r\n')[1:-1])
    return ""


def parse_program_thread(robot_msg: str, thread_num: int) -> ThreadState:
    res = ThreadState()
    lines = robot_msg.split("\r\n")[1:-1]
    res.thread_num = thread_num
    res.running = True
    res.name = lines[-1].split()[0]
    res.step_num = lines[-1].split()[2]
    for line in lines:
        if "Program is not running." in line:
            res.running = False
        elif "Completed cycles: " in line:
            res.completed_cycles = int(line.split()[-1])
        elif "Remaining cycles: " in line:
            res.remaining_cycles = -1 if "Infinite" in line else int(line.split()[-1])
            # break  # Because remaining cycles number always last
        elif "No program is running." in line:
            res.name = ""
            res.step_num = -1
            break
    return res


def parse_program_rcp(robot_msg: str) -> ThreadState:
    res = RCPState()
    lines = robot_msg.split("\r\n")[1:-1]
    res.thread_num = 0
    res.running = False
    res.name = lines[-1].split()[0]
    res.step_num = lines[-1].split()[2]

    # for element in lines:
    #     print("!!!!", element)

    for line in lines:
        if "Motor power " in line:
            # because if motor is ON - STATUS message isn't consist this state - default True
            if line.split()[-1] == 'OFF':
                res.motor_on = False
        elif "TEACH mode" in line:
            res.repeat_mode = False
        elif "REPEAT mode" in line:
            res.repeat_mode = True
            if "CYCLE START ON" in line:
                res.running = True
        elif "Monitor speed(%) " in line:
            res.monitor_speed = float(line.split()[-1])
        elif "Program speed(%) " in line:
            res.program_speed = float(line.split()[-1])  # check it - because in consist 2-nd value - line.split()[-2]
        elif "ALWAYS Accu.[mm] " in line:
            res.accuracy = float(line.split()[-1])
        # elif "Program is not running." in line: # It looks only while moving
        #     res.running = False
        elif "Completed cycles: " in line:
            res.completed_cycles = int(line.split()[-1])
        elif "Remaining cycles: " in line:
            res.remaining_cycles = -1 if "Infinite" in line else int(line.split()[-1])
        elif "No program is running." in line:
            res.name = ""
            res.step_num = -1
    return res


def get_pc_status(client: TCPSockClient, threads: int) -> [ThreadState]:
    """ Checks the status of a list of PC programs based on a packed integer representing threads to check.

    Args:
        client(TCPSockClient): Object representing open client socket
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
            client.send_msg(f"PCSTATUS {thread_num + 1}:")
            response = client.wait_recv(NEWLINE_MSG).decode()
            pc_thread_states[thread_num] = parse_program_thread(response, thread_num=thread_num+1)
    return pc_thread_states


def get_rcp_status(client: TCPSockClient) -> ThreadState:
    """ Checks the status of current active RCP program.
    Returns:
        ThreadState: data object, representing the status of an active RCP program."""
    client.send_msg("STATUS")
    return parse_program_rcp(client.wait_recv(NEWLINE_MSG).decode())


def init_loading(client: TCPSockClient) -> None:
    client.send_bytes(START_LOADING)
    res = client.wait_recv(b'Loading...(using.rcc)\r\n', SAVE_LOAD_ERROR)
    if SAVE_LOAD_ERROR in res:
        raise KHIProgTransmissionError("SAVE/LOAD in progress")  # TODO: Try to reset error


def process_response(client: TCPSockClient) -> bytes:
    errors = b""
    res = client.wait_recv(SYNTAX_ERROR, PROGRAM_IN_USE, PKG_RECV, NAME_CONFIRMATION, CONFIRM_TRANSMISSION)
    if NAME_CONFIRMATION in res:
        res = client.wait_recv(PKG_RECV, SYNTAX_ERROR, PROGRAM_IN_USE, CONFIRM_TRANSMISSION)

    while SYNTAX_ERROR in res:
        errors += res
        client.send_msg("0")
        client.wait_recv(b"0\r\n")
        res = client.wait_recv(PKG_RECV, SYNTAX_ERROR, CONFIRM_TRANSMISSION)

    if PROGRAM_IN_USE in res:
        raise KHIProgRunningError("")
    return errors


def upload_program(client: TCPSockClient, program_bytes: bytes) -> None:
    """ Uploads a program to the robot.
    Args:
        client(TCPSockClient): Object representing open client socket
        program_bytes (bytes): Binary representation of program to upload.
    Raises:
        KawaProgSyntaxError: If there are syntax errors in the uploaded program.
        KawaProgRunningError: If program you're trying to upload is in use and not killed
    Returns:
        None
    """
    num_packages = math.ceil(len(program_bytes) / UPLOAD_BATCH_SIZE)
    file_packages = [program_bytes[idx * UPLOAD_BATCH_SIZE: (idx + 1) * UPLOAD_BATCH_SIZE]
                     for idx in range(num_packages)] + [CANCEL_LOADING]

    init_loading(client)

    errors = b""
    for byte_package in file_packages:
        client.send_bytes(START_UPLOAD_SEQ + byte_package + END_UPLOAD_SEQ)
        errors += process_response(client)

    if errors:
        raise KHIProgSyntaxError(errors.split(SYNTAX_ERROR))


def delete_program(client: TCPSockClient, program_name: str) -> None:
    client.send_msg("DELETE/P/D " + program_name)
    client.wait_recv(CONFIRMATION_REQUEST)
    client.send_msg("1")
    res = client.wait_recv(b"1" + NEWLINE_MSG)
    if PROGRAM_IN_USE in res:
        raise KHIProgRunningError(program_name)
    elif PROG_IS_LOADED in res:
        raise KHIProgLoadedError(program_name)


def pc_execute(client: TCPSockClient, program_name: str, thread_num: int) -> None:
    """ Executes PC program on selected thread
    Args:
         client(TCPSockClient): Object representing open client socket
         program_name (str): Name of a PC program inside robot's memory to be executed
         thread_num (int): PC program thread
    Note:
         When trying to execute pc program which has motion commands in it (LMOVE, JMOVE),
         robot won't generate error until the instruction is reached.
    """
    client.send_msg(f"PCEXE {str(thread_num)}: {program_name}")
    res = client.wait_recv(NEWLINE_MSG)

    if PROG_NOT_EXIST in res:
        raise KHIProgNotExistError(program_name)
    elif PROGRAM_IN_USE in res:
        raise KHIProgRunningError(program_name)
    elif THREAD_IS_BUSY in res:
        raise KHIThreadBusyError(thread_num)


def pc_abort(client: TCPSockClient, threads: int) -> None:
    """ Aborts running PC programs on selected threads.
    Args: threads (int): An integer representing the threads to be checked for status.
                         See "status_pc" for more info
    """
    for thread_num in range(5):
        if threads & (1 << thread_num):
            client.send_msg(f"PCABORT {thread_num + 1}:")
            client.wait_recv(NEWLINE_MSG)


def pc_end(client: TCPSockClient, threads: int) -> None:
    """ Softly ends selected program(s) waiting for the current cycle to be completed """
    for thread_num in range(5):
        if threads & (1 << thread_num):
            client.send_msg(f"PCEND {thread_num + 1}:")
            client.wait_recv(NEWLINE_MSG)


def pc_kill(client: TCPSockClient, threads: int) -> None:
    """ Unloads aborted programs from selected pc threads """
    for thread_num in range(5):
        if threads & (1 << thread_num):
            client.send_msg(f"PCKILL {thread_num + 1}:")
            client.wait_recv(CONFIRMATION_REQUEST)
            client.send_msg("1\n")
            res = client.wait_recv(NEWLINE_MSG)
            if PROG_IS_ACTIVE in res:
                raise KHIProgActiveError(thread_num + 1)


def rcp_prepare(client: TCPSockClient, program_name: str):
    """ Prepare RCP program for execution (open on Teach pendant) """
    client.send_msg("PRIME " + program_name)
    res = client.wait_recv(NEWLINE_MSG)

    if PROG_NOT_EXIST in res:
        raise KHIProgNotExistError(program_name)


def rcp_execute(client: TCPSockClient, program_name: str, blocking=True):
    """ Executes RCP program of set name """
    client.send_msg("EXECUTE " + program_name)
    res = client.wait_recv(NEWLINE_MSG)

    if PROG_NOT_EXIST in res:
        raise KHIProgNotExistError(program_name)
    elif TEACH_MODE_ON in res:
        raise KHITeachModeError
    elif TEACH_LOCK_ON in res:
        raise KHITeachLockError
    elif MOTORS_DISABLED in res:
        raise KHIMotorsOffError
    elif VARIABLE_NOT_DEFINED in res:
        raise KHIVarNotDefinedError
    elif ERROR_NOW in res:
        raise KHIEResetError

    if blocking:
        client.set_timeout(None)
        res = client.wait_recv(PROGRAM_STOPPED)
        if VARIABLE_NOT_DEFINED in res:
            client.reset_timeout()
            raise KHIVarNotDefinedError
        elif WELDER_ERROR_1 in res:
            client.reset_timeout()
            raise KHIWelderError
        elif PROGRAM_HELD in res:
            client.reset_timeout()
            raise KHIProgramHeldError(' '.join(res.decode('utf-8').split()))

        client.reset_timeout()
        if PROGRAM_COMPLETED in res:
            return

        # client.wait_recv(PROGRAM_COMPLETED)


def rcp_prime(client: TCPSockClient, program_name: str, blocking=True):
    client.send_msg("PRIME " + program_name)
    res = client.wait_recv(NEWLINE_MSG)

    if PROG_NOT_EXIST in res:
        raise KHIProgNotExistError(program_name)


def rcp_abort(client: TCPSockClient) -> None:
    """ Aborts current RCP program """
    client.send_msg("ABORT")
    client.wait_recv(NEWLINE_MSG)


def rcp_hold(client: TCPSockClient) -> None:
    """ Holds current RCP program """
    client.send_msg("HOLD")
    client.wait_recv(NEWLINE_MSG)


# def rcp_continue(client: TCPSockClient) -> None:
#     """ Continue current RCP program """
#     client.send_msg("CONTINUE")
#     client.wait_recv(NEWLINE_MSG)

def rcp_continue(client: TCPSockClient, blocking=True):
    """ Continue current RCP program """
    client.send_msg("CONTINUE")
    res = client.wait_recv(NEWLINE_MSG)

    if TEACH_MODE_ON in res:
        raise KHITeachModeError
    elif TEACH_LOCK_ON in res:
        raise KHITeachLockError
    elif MOTORS_DISABLED in res:
        raise KHIMotorsOffError
    elif VARIABLE_NOT_DEFINED in res:
        raise KHIVarNotDefinedError
    elif ERROR_NOW in res:
        raise KHIEResetError

    if blocking:
        client.set_timeout(None)
        res = client.wait_recv(PROGRAM_STOPPED)
        if VARIABLE_NOT_DEFINED in res:
            client.reset_timeout()
            raise KHIVarNotDefinedError
        elif WELDER_ERROR_1 in res:
            client.reset_timeout()
            raise KHIWelderError
        elif PROGRAM_HELD in res:
            client.reset_timeout()
            raise KHIProgramHeldError(' '.join(res.decode('utf-8').split()))

        client.reset_timeout()
        if PROGRAM_COMPLETED in res:
            return


def kill_rcp(client: TCPSockClient) -> None:
    """ Kills current RCP program """
    client.send_msg("KILL")
    client.wait_recv(CONFIRMATION_REQUEST)
    client.send_msg("1")
    client.wait_recv(NEWLINE_MSG)


def read_variable_real(client: TCPSockClient, variable_name: str) -> float:
    client.send_msg(f"list /r {variable_name}")
    tmp_string = client.wait_recv(NEWLINE_MSG)
    real_variable = float(tmp_string.split()[-2])
    return real_variable


def read_programs_list(client: TCPSockClient) -> [str]:
    # DEV check this function for long size pg lists
    handshake(client)
    client.send_msg("DIRECTORY/P")
    res = client.wait_recv(NEWLINE_MSG).decode().split("\r\n")
    if len(res) > 3:
        pg_list_str = res[2]
        pg_list = [item.strip() for item in pg_list_str.split() if item.strip() != ""]
        return pg_list
    else:
        return []


def pg_delete(client: TCPSockClient, program_name):
    client.send_msg(f"DELETE/D {program_name}")
    client.wait_recv(CONFIRMATION_REQUEST)
    client.send_msg("1\n")
    res = client.wait_recv(NEWLINE_MSG)

    if RCP_IS_RUNNING in res:
        raise KHIProgRunningError(program_name)
    elif PROG_IS_LOADED in res:
        raise KHIProgLoadedError(program_name)


def reset_save_load(client: TCPSockClient):
    client.send_bytes(b"\x02\x43\x20\x20\x20\x20\x30" + "END.".encode() + b"\x17")
    client.send_bytes(CANCEL_LOADING)
    client.wait_recv(CONFIRM_TRANSMISSION)


def pack_threads(*threads):
    return sum(1 << (thread_num - 1) for thread_num in threads)


def signal_out(client: TCPSockClient, signal):
    client.send_msg(f"SOUT {signal}")


if __name__ == "__main__":
    IP = "127.0.0.1"    # IP for K-Roset
    PORT = 9105         # Port for K-Roset
