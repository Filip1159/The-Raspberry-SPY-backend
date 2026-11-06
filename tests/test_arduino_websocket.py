import asyncio

from app.websocket_manager import WebsocketManager


class FakeDevice:
    remote_address = ('192.168.1.50', 1234)

    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


def test_it_is_off_by_default():
    manager = WebsocketManager(enabled=False)

    manager.start()

    assert not hasattr(manager, '_thread')


def test_sending_awaits_the_device_and_reports_when_nobody_is_connected():
    manager = WebsocketManager(enabled=True)
    assert asyncio.run(manager.send('TOGGLE_LED')) is False

    device = FakeDevice()
    manager.connected_device = device
    assert asyncio.run(manager.send('TOGGLE_LED')) is True
    assert device.sent == ['TOGGLE_LED']
