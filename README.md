# khi_robot_py
Python library for Kawasaki Robotics

khirolib based on reversed engineering **KIDE** protocol commands.
Now it works for uploading AS-programs, RCP-programs (Robot Control Program) using the 'LOAD using.rcc' command.
khirolib supports uploading large-sized AS-programs and indication if error in AS-program found.

It should be fast and not much dependent on file size.

Now it works excellent with real robot and K-Roset simulator.

Library supports: 
- Uploading PC/RCP-programs
- RCP-execution
- PC-execution (with ERESET, MOTOR ON, TEACH mode check etc.)
- Status PC/RCP commands
- Abort&Kill PC/RPC commands

See example.py file.
#
### Announcement!!
**If anyone knows how to remove the error 'P2076' 'SAVE/LOAD in progress' - please write issue!**
#

Working modes (_connection_mode_ argument):
- _single_ mode - every command requires reconnection
* _continuous_ mode - robot always connected to PC

## Install
```
git clone https://github.com/IgorMIV/khi_robot_py.git
cd khi_robot_py
# or
pip install --user --break-system-packages git+https://github.com/IgorMIV/khi_robot_py.git
```

## Usage

```python
from khirolib import *

# Establish connection with robot on specific ip and port:
robot = khirolib(IP, PORT, connection_mode='single')

# Upload program from file:
robot.upload_program(filename="as_programs/endless.as")
robot.upload_program(filename="as_programs/endless_move.as")

# Upload program from string:
robot.upload_program(program_name="prog", program_text=program_text)
# where string is:
program_text = "var1 = 10\n" \
               "POINT loc1 = TRANS(100, 100, 100, 100)"

# Call PC-program execution by name in thread number 3:
robot.execute_pc(program_name="endless", thread=3)

# Call RCP-program execution:
robot.execute_rcp("endless_move")

# Aborting and killing PC-program execution:
result = robot.abort_pc(program_name='endless')
print(result)
result = robot.kill_pc(program_name='endless')
print(result)

# The following commands will only work some time after the program is started:
# robot.abort_rcp()
# robot.kill_rcp()

# Reading status PC and RCP programs:
rcp_status = robot.status_rcp()
print(rcp_status)

pc_status = robot.status_pc()
print(pc_status)
