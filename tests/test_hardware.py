from app.gpio.navigation import Navigation
from app.hardware import get_hardware
from app.hardware.fake import FakeLcd
from app.melody_player import MELODIES
from app.services import get_services
from app.system_stats import get_cpu_percent, get_cpu_temperature, get_ram_usage


def test_hardware_is_simulated_in_tests():
    assert isinstance(get_hardware().lcd, FakeLcd)


def test_servos_stay_within_limits():
    servos_controller = get_services().servos_controller
    servos_controller.move('CENTER')
    for _ in range(100):
        servos_controller.move('UP_LEFT')

    assert servos_controller.vertical_servo_angle == -30
    assert servos_controller.horizontal_servo_angle == 30
    servos_controller.move('CENTER')
    assert servos_controller.vertical_servo_angle == 0


def test_lcd_shows_the_menu():
    hardware = get_hardware()
    services = get_services()
    navigation = Navigation(
        hardware.lcd,
        hardware.encoder,
        hardware.button,
        services.servos_controller,
        hardware.camera_light,
        services.alarm_manager,
        services.melody_player,
        hardware.climate_sensor,
    )

    navigation.loop()
    assert hardware.lcd.lines()[0].startswith('Hello Raspberry!')

    hardware.button.press()
    navigation.loop()
    navigation.loop()
    assert hardware.lcd.lines()[0].startswith('> Camera')


def test_climate_sensor_produces_readings():
    sensor = get_hardware().climate_sensor
    sensor.start()

    assert sensor.temperature is not None
    assert sensor.humidity is not None
    assert sensor.voltage is not None
    assert sensor.last_updated is not None


def test_system_stats_are_numbers():
    assert 0 <= get_cpu_percent() <= 100
    assert isinstance(get_cpu_temperature(), int)
    assert 0 <= get_ram_usage() <= 100


def test_melodies_can_be_played_on_the_fake_buzzer():
    melody_player = get_services().melody_player
    melody_player.play(next(iter(MELODIES)))
    assert melody_player.is_playing()
    melody_player.stop()
    assert not melody_player.is_playing()
