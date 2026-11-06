from datetime import datetime, timedelta

import pytest

from app.climate import STALE_AFTER_SECONDS, ClimateReadings, parse_reading


def test_parses_what_the_sensor_sends():
    assert parse_reading('H=45.2;T=22.1;V=3.00') == (45.2, 22.1, 3.0)
    assert parse_reading('H=45.2;T=-3.5;V=2.95\r\n') == (45.2, -3.5, 2.95)


@pytest.mark.parametrize(
    'garbage',
    [
        '',
        'READY',
        'H=45.2;T=22.1',
        'H=abc;T=22.1;V=3.0',
        'H=45.2;T=22.1;V=',
        'H=45.2;X=22.1;V=3.0',
        '\x00\xff;;',
        'H=150;T=22.1;V=3.0',
        'H=45;T=22;V=-1',
    ],
)
def test_malformed_or_implausible_packets_give_none_instead_of_raising(garbage):
    assert parse_reading(garbage) is None


def test_a_bad_packet_keeps_the_previous_values():
    readings = ClimateReadings()
    assert readings.apply_text('H=40.0;T=21.0;V=3.00')
    first_update = readings.last_updated

    assert not readings.apply_text('H=4')

    assert (readings.humidity, readings.temperature, readings.voltage) == (40.0, 21.0, 3.0)
    assert readings.last_updated == first_update


def test_there_is_no_data_before_the_first_reading_and_it_goes_stale():
    readings = ClimateReadings()
    assert readings.stale

    readings.apply_text('H=40.0;T=21.0;V=3.00')
    assert not readings.stale

    readings.last_updated = datetime.now() - timedelta(seconds=STALE_AFTER_SECONDS + 5)
    assert readings.stale
