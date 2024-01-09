
ROBOT_STATE_VARS = (("motor_power", "SWITCH POWER"),
                    ("cycle_start", "SWITCH CS"),
                    ("rgso", "SWITCH RGSO"),
                    ("error", "SWITCH ERROR"),
                    ("repeat", "SWITCH REPEAT"),
                    ("run", "SWITCH RUN"))


class RobotState:
    """
    Represents the state of a Kawasaki robot, providing information about various internal variables.

    Attributes:
    - 'motor_power' (bool): Indicates the current state of the motor power (ON/OFF).
    - 'cycle_start' (bool): Indicates the state of the cycle start switch (ON/OFF).
    - 'rgso' (bool): Displays if servos are powered or not
    - 'repeat' (bool): Indicates the state of the repeat switch (ON/OFF).
    - 'run' (bool): Indicates the state of the run switch (ON/OFF).
    - 'error' (bool): Indicates whether an error is detected.
    - 'error_descr' (str): Provides the description of any detected error.
    """

    motor_power: bool
    cycle_start: bool
    rgso: bool
    repeat: bool
    run: bool
    error: bool
    error_descr: str
