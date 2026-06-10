from datetime import datetime
from RPLCD.i2c import CharLCD
from gpiozero import Button, CPUTemperature, PWMLED, RotaryEncoder
from threading import Timer, Thread
from time import sleep
from app.alarm_manager import alarm_manager
from app.bluetooth_manager import ble_manager
from app.melody_player import melody_player
from app.gpio.navigation import Navigation
from app.gpio.servos_controller import servos_controller
import os


LED_TRIGGER = "/sys/class/leds/ACT/trigger"
LED_BRIGHTNESS = "/sys/class/leds/ACT/brightness"


camera_light = PWMLED(14)
lcd = CharLCD('PCF8574', 0x27, backlight_enabled=True)
encoder = RotaryEncoder(a=17, b=27, max_steps=0)
button = Button(22, pull_up=True)

navigation = Navigation(lcd, encoder, button, servos_controller, camera_light, alarm_manager, melody_player, ble_manager)


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
                os.system(f"echo 0 | sudo tee {LED_BRIGHTNESS} > /dev/null")
            if seconds_without_activity > 5:
                lcd.backlight_enabled = False
                os.system(f"echo 1 | sudo tee {LED_BRIGHTNESS} > /dev/null")
            sleep(0.1)
    finally:
        os.system(f"echo default-off | sudo tee {LED_TRIGGER} > /dev/null")


os.system(f"echo none | sudo tee {LED_TRIGGER} > /dev/null")

navigation_thread = Thread(target=navigation_loop, daemon=True)
navigation_thread.start()


# # Ścieżki do kontroli diody zasilania (PWR)
# # Uwaga: W zależności od wersji systemu, folder może nazywać się 'pwr' lub 'led1'
# LED_TRIGGER = "/sys/class/leds/PWR/trigger"
# LED_BRIGHTNESS = "/sys/class/leds/PWR/brightness"

# def setup_led():
#     # Przełączamy diodę w tryb manualny (none)
#     # Wymaga uruchomienia skryptu z uprawnieniami sudo
#     os.system(f"echo none | sudo tee {LED_TRIGGER} > /dev/null")

# def set_led(state):
#     # state: 1 = włączona, 0 = wyłączona
#     os.system(f"echo {state} | sudo tee {LED_BRIGHTNESS} > /dev/null")

# def cleanup_led():
#     # Przywracamy domyślne zachowanie diody (sygnalizacja zasilania/default-on)
#     os.system(f"echo default-off | sudo tee {LED_TRIGGER} > /dev/null")

# try:
#     print("Przejmowanie kontroli nad diodą...")
#     setup_led()
    
#     print("Miganie diodą przez 5 sekund...")
#     for _ in range(5):
#         set_led(1)  # Włącz
#         sleep(0.5)
#         set_led(0)  # Wyłącz
#         sleep(0.5)

# finally:
#     print("Przywracanie domyślnego stanu diody...")
#     cleanup_led()
