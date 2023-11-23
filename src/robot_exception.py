
class RobotConnException(ConnectionError):
    def __init__(self):
        super().__init__("Can't establish connection with robot!")
