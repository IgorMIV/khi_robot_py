from khirolib import *

IP = "127.0.0.1"    # IP for K-Roset
PORT = 9105         # Port for K-Roset

robot = khirolib(IP, PORT, connection_mode='single', log=False)
result = robot.upload_program(filename="as_programs/large.as", kill_current_program=True)

program_text = "var1 = 10\n" \
               "POINT loc1 = TRANS(100, 100, 100, 100)"
robot.upload_program(program_name="prog", program_text=program_text, kill_current_program=True)

robot.execute_program('large')

