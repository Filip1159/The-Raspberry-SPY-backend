from threading import Thread
from time import sleep

from app.gpio.navigation import Navigation
from app.hardware import get_hardware
from app.services import get_services

# The local interface: 20x4 LCD + rotary encoder. It also dims the LCD backlight and the on-board LED after a while.


def start_local_interface():
    hardware = get_hardware()
    services = get_services()
    lcd = hardware.lcd
    status_led = hardware.status_led

    navigation = Navigation(
        lcd,
        hardware.encoder,
        hardware.button,
        services.servos_controller,
        hardware.camera_light,
        services.alarm_manager,
        services.melody_player,
        hardware.climate_sensor,
    )

    def navigation_loop():
        try:
            seconds_without_activity = 0
            while True:
                delta = navigation.loop()
                if delta == 0 and seconds_without_activity < 10:
                    seconds_without_activity += 0.1
                elif delta != 0:
                    seconds_without_activity = 0
                    lcd.backlight_enabled = True
                    status_led.set(False)
                if seconds_without_activity > 5:
                    lcd.backlight_enabled = False
                    status_led.set(True)
                sleep(0.1)
        finally:
            status_led.release()

    status_led.take_control()
    Thread(target=navigation_loop, daemon=True).start()
