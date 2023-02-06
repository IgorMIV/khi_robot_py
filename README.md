# khi_robot_py
Python library for Kawasaki Robotics

khirolib based on reversed engineering **KIDE** protocol commands.
Now it works only for uploading AS-programs using the 'LOAD using.rcc' command.
khirolib supports uploading large-sized AS-programs.

It should be fast and not much dependent on file size.

Now it works excellent with K-Roset simulator and I will test it with real robot in near future.

In the future, I plan to implement support for working with PC-programs too.

See example.py file.

Working modes (_connection_mode_ argument):
- _single_ mode - every command requires reconnection
* _continuous_ mode - robot always connected to PC

## Usage

```python
from khirolib import *

# Establish connection with robot on specific ip and port
robot = khirolib(IP, PORT, connection_mode='single')

# Upload program from file
robot.upload_program(filename="as_programs/test.as", kill_current_program=True)

#Upload program from string
robot.upload_program(program_name="prog", program_text=program_text, kill_current_program=True)
# where string is:
program_text = "var1 = 10\n" \
               "POINT loc1 = TRANS(100, 100, 100, 100)"

# Call program execution by name
robot.execute_program('test')