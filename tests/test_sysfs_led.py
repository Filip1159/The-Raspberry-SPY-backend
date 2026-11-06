from app.hardware.sysfs_led import ActLed


def test_writes_straight_to_sysfs_without_sudo(tmp_path):
    trigger, brightness = tmp_path / 'trigger', tmp_path / 'brightness'
    led = ActLed(trigger, brightness)

    led.take_control()
    assert trigger.read_text() == 'none'
    led.set(True)
    assert brightness.read_text() == '1'
    led.set(False)
    assert brightness.read_text() == '0'
    led.release()
    assert trigger.read_text() == 'default-off'


def test_without_permission_the_led_is_left_alone_and_logged_once(tmp_path, caplog):
    missing = tmp_path / 'no-such-dir' / 'brightness'  # writing fails like a root-only file does
    led = ActLed(missing, missing)

    led.set(True)
    led.set(False)
    led.release()

    assert len([record for record in caplog.records if 'ACT LED' in record.message]) == 1
