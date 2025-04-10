from khirolib import KHIRoLibLite
import asyncio

IP = "192.168.12.2"    # IP for K-Roset
# IP = "192.168.0.2"    # IP for real robot

async def main():
    robot = KHIRoLibLite(IP)

    program_text = (f"point .l1 = HERE\n"
                    f"point .l2 = SHIFT(.l1 by -100,0,0)\n"
                    f"SPEED 50 mm/s ALWAYS\n"
                    f"JMOVE .l1\n"
                    f"JMOVE .l2\n"
                    f"JMOVE .l1\n")

    robot.upload_program(program_name="test_pg",
                         program_text=program_text,
                         open_program=True)

    # await robot.execute_rcp(program_name="test_pg", blocking=False)

    # Future problems:
    #  In K-Roset simulation - prepare_rcp_program after upload_program will not change program on the teach
    #  pendant, but in fact - it will be a new program - you can check it if try change active line manually

asyncio.run(main())