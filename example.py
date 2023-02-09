from khirolib import *

IP = "127.0.0.1"    # IP for K-Roset
PORT = 9105         # Port for K-Roset

robot = khirolib(IP, PORT, connection_mode='single', log=True)

result = robot.upload_program_experimental(filename="as_programs/endless.as", kill_current_program=True)
result = robot.upload_program_experimental(filename="as_programs/large.as", kill_current_program=True)

program_text = "var1 = 10\n" \
               "POINT loc1 = TRANS(100, 100, 100, 100)"
robot.upload_program_experimental(program_name="prog", program_text=program_text, kill_current_program=False)

robot.execute_pc_program(program_name="endless", thread=2)

pc_status = robot.status_pc()
print(pc_status)

result = robot.abort_pc(program_name='endless')
print(result)

result = robot.kill_pc(program_name='endless')
print(result)
