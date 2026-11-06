from enum import Enum, auto

from app.hardware.interfaces import PwmChannel


class Direction(Enum):
    UP_LEFT = auto()
    UP = auto()
    UP_RIGHT = auto()
    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()
    DOWN_LEFT = auto()
    DOWN = auto()
    DOWN_RIGHT = auto()


def to_pwm(angle):  # duty = 0.5ms --- 2.5ms, T = 20ms, % = 2.5 --- 12.5
    return 2.5 + angle / 180 * 10


V_CENTER = 70
H_CENTER = 80


MAX_DEVIATION = 30


class ServosController:
    def __init__(self, vertical_servo: PwmChannel, horizontal_servo: PwmChannel):
        self.vertical_servo = vertical_servo
        self.vertical_servo_angle = 0
        self.vertical_servo.start(to_pwm(V_CENTER))
        self.horizontal_servo = horizontal_servo
        self.horizontal_servo_angle = 0
        self.horizontal_servo.start(to_pwm(H_CENTER))

    def move(self, direction: str):
        dir = Direction[direction]
        match dir:
            case Direction.UP_LEFT:
                self.try_go_up(1)
                self.try_go_left(1)
            case Direction.UP:
                self.try_go_up(1)
            case Direction.UP_RIGHT:
                self.try_go_up(1)
                self.try_go_right(1)
            case Direction.LEFT:
                self.try_go_left(1)
            case Direction.CENTER:
                self.vertical_servo_angle = 0
                self.vertical_servo.change_duty_cycle(to_pwm(V_CENTER))
                self.horizontal_servo_angle = 0
                self.horizontal_servo.change_duty_cycle(to_pwm(H_CENTER))
            case Direction.RIGHT:
                self.try_go_right(1)
            case Direction.DOWN_LEFT:
                self.try_go_down(1)
                self.try_go_left(1)
            case Direction.DOWN:
                self.try_go_down(1)
            case Direction.DOWN_RIGHT:
                self.try_go_down(1)
                self.try_go_right(1)

    def try_go_up(self, diff):
        new_angle = max(-MAX_DEVIATION, self.vertical_servo_angle - diff)
        if self.vertical_servo_angle != new_angle:
            self.vertical_servo_angle = new_angle
            self.vertical_servo.change_duty_cycle(to_pwm(V_CENTER + self.vertical_servo_angle))

    def try_go_down(self, diff):
        new_angle = min(MAX_DEVIATION, self.vertical_servo_angle + diff)
        if self.vertical_servo_angle != new_angle:
            self.vertical_servo_angle = new_angle
            self.vertical_servo.change_duty_cycle(to_pwm(V_CENTER + self.vertical_servo_angle))

    def try_go_left(self, diff):
        new_angle = min(MAX_DEVIATION, self.horizontal_servo_angle + diff)
        if self.horizontal_servo_angle != new_angle:
            self.horizontal_servo_angle = new_angle
            self.horizontal_servo.change_duty_cycle(to_pwm(H_CENTER + self.horizontal_servo_angle))

    def try_go_right(self, diff):
        new_angle = max(-MAX_DEVIATION, self.horizontal_servo_angle - diff)
        if self.horizontal_servo_angle != new_angle:
            self.horizontal_servo_angle = new_angle
            self.horizontal_servo.change_duty_cycle(to_pwm(H_CENTER + self.horizontal_servo_angle))
