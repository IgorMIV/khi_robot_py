from src.khi_telnet_lib import telnet_connect, TCPSockClient

from src.khi_telnet_lib import get_pc_status, get_rcp_status, upload_program, kill_rcp, \
                                pc_abort, pc_kill, handshake,\
                                rcp_prepare, rcp_execute, rcp_hold, \
                                pc_execute, \
                                read_programs_list, pg_delete, ereset

import config.robot as robot_config

TELNET_DEF_PORT = 23
TELNET_SIM_PORT = 9105


class KHIRoLibLite:
    def __init__(self, ip: str):
        self._ip = ip

        self._is_real_robot = True if ip != '127.0.0.1' else False
        self._telnet_port = TELNET_DEF_PORT if self._is_real_robot else TELNET_SIM_PORT

        self._telnet_client = None

        self._connect()

    def _connect(self):
        """ Connection sequence to the robot."""
        self._telnet_client = TCPSockClient(self._ip, self._telnet_port)
        telnet_connect(self._telnet_client)

        # if self._is_real_robot:
        #     # Check for running tcp-ip process
        #     self._tcpip_client = TCPSockClient(self._ip, self._tcpip_port)

        # self.start()

    def close(self):
        """ Close sequence for robot.
        Used explicitly to close all connections or when __del__ is called
        """
        self._telnet_client.disconnect()

    def _get_active_programs_names(self):
        pg_status_list = self.get_status_pc()
        rcp_status = get_rcp_status(self._telnet_client)

    def ereset(self):
        ereset(self._telnet_client)

    def get_status_pc(self, thread_num=None):
        if thread_num is None:
            threads_info_list = get_pc_status(self._telnet_client, 31)
            return threads_info_list
        else:
            return get_pc_status(self._telnet_client, 1 << (thread_num-1))

    def upload_program(self, program_name, program_text):
        pg_status_list = self.get_status_pc()
        rcp_status = get_rcp_status(self._telnet_client)

        for element in pg_status_list:
            if element.is_exist:
                if element.name == program_name:  # добавить регистр
                    print("Bingo", element.name, element.is_running, element.thread_num)
                    if element.is_running:
                        pc_abort(self._telnet_client, 1 << (element.thread_num-1))
                    pc_kill(self._telnet_client, 1 << (element.thread_num-1))
                    break  # because we have only 1 active program with the same name

        if rcp_status.is_exist:
            if rcp_status.name == program_name:  # добавить регистр
                if rcp_status.is_running:
                    rcp_hold(self._telnet_client)
                kill_rcp(self._telnet_client)

        # Uploading program block
        file_string = '.PROGRAM ' + program_name + '\n'
        file_string += program_text + '\n'
        file_string += '.END' + '\n'

        program_bytes = bytes(file_string, 'utf-8')
        upload_program(self._telnet_client, program_bytes)

    def prepare_rcp(self, program_name):
        rcp_prepare(self._telnet_client, program_name)

    def execute_rcp(self, program_name, blocking=True):
        rcp_execute(self._telnet_client, program_name, blocking)

    def execute_pc(self, program_name, thread_num):
        pc_execute(self._telnet_client, program_name, thread_num)

    def stop_and_kill_pc(self, thread_num):
        pc_abort(self._telnet_client, 1 << (thread_num - 1))
        pc_kill(self._telnet_client, 1 << (thread_num - 1))

    def read_all_programs(self):
        programs_list = read_programs_list(self._telnet_client)
        return programs_list

    def delete_programs(self, pg_list: list, force=False):
        # DEV удалить из списка pg_list имена, которые упоминаются в robot_config.protected_pg_list
        if len(pg_list) == 0:
            return

        if force:
            rcp_status = get_rcp_status(self._telnet_client)
            if rcp_status.is_exist:
                if rcp_status.name in pg_list:  # добавить регистр
                    if rcp_status.is_running:
                        rcp_hold(self._telnet_client)
                    kill_rcp(self._telnet_client)

            # DEV Add pc programs

        for pg_name in pg_list:
            pg_delete(self._telnet_client, pg_name)
