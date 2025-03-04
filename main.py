from khirolib import KHIRoLibLite
import time

IP = "127.0.0.1"    # IP for K-Roset
# IP = "192.168.0.2"    # IP for real robot

robot = KHIRoLibLite(IP)

program_text = 'point .l1 = HERE\n' \
               'point .l2 = SHIFT(.l1 by -100,0,0)\n' \
               'SPEED 30 mm/s ALWAYS\n' \
               'JMOVE .l1\n' \
               'JMOVE .l2\n' \
               'JMOVE .l1\n'

result = robot.upload_program(program_name="kep",
                              program_text=program_text)

robot.prepare_rcp(program_name="kep")

robot.execute_rcp(program_name="kep")

# # robot.execute_pc('kep4', 5)
#
# # robot.stop_and_kill_pc(5)  # Read all не работает после этой операции если сразу
#
# for i in range(5):
#     result = robot.upload_program(program_name="kep{0}".format(i),
#                                   program_text=program_text)
# pg_list = robot.read_all_programs()
#
# print("PG LIST", pg_list)
# robot.delete_programs(pg_list, force=True)
#
# #  In K-Roset simulation - prepare_rcp_program after upload_program will not change program on the teach
# #  pendant, but in fact - it will be a new program - you can check it if try change active line manually
