from khirolib import *

IP = "127.0.0.1"    # IP for K-Roset
PORT = 9105         # Port for K-Roset22222222222222222

robot = khirolib(IP, PORT, connection_mode='single', log=True)

result = robot.upload_program(filename="as_programs/endless.as")
result = robot.upload_program(filename="as_programs/endless_move.as")
result = robot.upload_program(filename="as_programs/large.as")

program_text = "var1 = 10\n" \
               "POINT loc1 = TRANS(100, 100, 100, 100)"
robot.upload_program(program_name="prog", program_text=program_text)

robot.execute_pc(program_name="endless", thread=3)

robot.execute_rcp("endless_move")

result = robot.abort_pc(program_name='endless')
print(result)

result = robot.kill_pc(program_name='endless')
print(result)

# The following commands will only work some time after the program is started:
# robot.abort_rcp()
# robot.kill_rcp()

rcp_status = robot.status_rcp()
print(rcp_status)

pc_status = robot.status_pc()
print(pc_status)
