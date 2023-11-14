from khirolib import *

IP = "127.0.0.1"    # IP for K-Roset
PORT = 9105         # Port for K-Roset

with khirolib(IP, PORT, log=True) as robot:

    program_text = ""
    for i in range(1000):
        program_text += "POINT loc1 = TRANS(0, 0, {0})\n".format(i)

    for i in range(100):

        result = robot.upload_program(program_name="prog{0}.as".format(i),
                                      program_text=program_text)
        print("sent program ", i)

    # result = robot.upload_program(filename="as_programs/endless.as")
    # result = robot.upload_program(filename="as_programs/endless_move.as")
    #
    # program_text = "var1 = 10\n" \
    #                "POINT loc1 = TRANS(100, 100, 100, 100)"
    # robot.upload_program(program_name="prog", program_text=program_text)
    #
    # robot.execute_pc(program_name="endless", thread=3)
    #
    # robot.execute_rcp("endless_move")
    #
    # result = robot.abort_pc(program_name='endless')
    # print(result)
    #
    # result = robot.kill_pc(program_name='endless')
    # print(result)  #
    #
    # # rcp_status = robot.status_rcp()
    # # print(rcp_status)
    #
    # pc_status = robot.status_pc()
    # print(pc_status)
