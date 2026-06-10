from datetime import datetime
from threading import Timer
from RPLCD.i2c import CharLCD
from gpiozero import Button, PWMLED, RotaryEncoder
from time import sleep

from app.bluetooth_manager import BluetoothManager
from app.gpio.servos_controller import ServosController
from app.alarm_manager import AlarmManager
from app.melody_player import MELODIES, MelodyPlayer
from app.system_stats import get_cpu_percent, get_cpu_temperature, get_ram_usage


class Navigation:

    def __init__(self, lcd: CharLCD, encoder: RotaryEncoder, encoder_button: Button, servos_controller: ServosController,
                    camera_light: PWMLED, alarm_manager: AlarmManager, melody_player: MelodyPlayer, ble_manager: BluetoothManager):
        self.__lcd = lcd
        self.__encoder = encoder
        self.__encoder_button = encoder_button
        self.__servos_controller = servos_controller
        self.__camera_light = camera_light
        self.__alarm_manager = alarm_manager
        self.__melody_player = melody_player
        self.__ble_manager = ble_manager
        self.__selected_index = 0
        self.__old_selected_index = 0
        self.__menu_offset = 0
        self.__last_encoder_step = 0
        self.__active_view = 'hello'
        self.__old_active_view = 'hello'
        self.__scroll_alternative_function = None
        self.__selected_alarm_day = None
        self.__alarm_details_hour = None
        self.__alarm_details_minute = None
        self.__alarm_details_enabled = None
        self.__alarm_details_melody = None


    def loop(self):
        delta = self.__encoder.steps - self.__last_encoder_step
        self.__last_encoder_step = self.__encoder.steps
        match self.__scroll_alternative_function:
            case None:
                if self.__active_view in [ 'menu', 'camera', 'alarms', 'alarm_details' ]:
                    self.__selected_index = max(0, min(self.__selected_index + delta, self.__get_items_count() - 1))
                    if self.__selected_index < self.__menu_offset:
                        self.__menu_offset = self.__selected_index
                    elif self.__selected_index >= self.__menu_offset + 4:
                        self.__menu_offset = self.__selected_index - 3
            case 'vertical':
                if delta > 0:
                    self.__servos_controller.try_go_up(delta)
                elif delta < 0:
                    self.__servos_controller.try_go_down(-delta)
            case 'horizontal':
                if delta > 0:
                    self.__servos_controller.try_go_left(delta)
                elif delta < 0:
                    self.__servos_controller.try_go_right(-delta)
            case 'brightness':
                self.__camera_light.value = min(1, max(0, self.__camera_light.value + float(delta) / 10))
            case 'set_hour':
                self.__alarm_details_hour = (self.__alarm_details_hour + delta) % 24
            case 'set_minute':
                self.__alarm_details_minute = (self.__alarm_details_minute + delta) % 60
            case 'alarm_melody':
                melodies_list = list(MELODIES.keys())
                melodies_list.sort()
                current_melody_idx = melodies_list.index(self.__alarm_details_melody)
                self.__alarm_details_melody = melodies_list[(current_melody_idx + delta) % len(melodies_list)]

        self.__draw_active_view()
        return delta

    
    def __draw_active_view(self):
        if self.__old_active_view != self.__active_view:
            self.__old_active_view = self.__active_view
            self.__lcd.clear()
            self.__selected_index = 0
            self.__menu_offset = 0
        
        match self.__active_view:
            case 'hello':
                self.__draw_formatted_lcd_lines(self.__hello_content(), False)
            case 'menu':
                self.__draw_formatted_lcd_lines(self.__menu_content(), True)
            case 'camera':
                self.__draw_formatted_lcd_lines(self.__camera_content(), True)
            case 'alarms':
                self.__draw_formatted_lcd_lines(self.__alarms_content(), True)
            case 'alarm_details':
                self.__draw_formatted_lcd_lines(self.__alarm_details_content(), True)
            case 'stats':
                self.__draw_formatted_lcd_lines(self.__stats_content(), False)
            case 'ble_climate':
                self.__draw_formatted_lcd_lines(self.__ble_climate_view_content(), False)


    def __draw_formatted_lcd_lines(self, content, scrollable: bool):
        for i in range(4):
            item_index = self.__menu_offset + i
            if item_index >= len(content):
                break

            prefix = "> " if scrollable and item_index == self.__selected_index else ""
            self.__lcd.cursor_pos = (i, 0)
            self.__lcd.write_string(prefix)
            formatted = content[item_index]['template'].format(*content[item_index]['args'])
            self.__lcd.write_string(formatted.ljust(20 - len(prefix)))

        if self.__scroll_alternative_function is None:
            self.__encoder_button.when_pressed = content[self.__selected_index]['action']


    def __hello_content(self):
        return [ 
            { 'template': 'Hello Raspberry!', 'args': [], 'action': lambda: self.__set_active_view('menu') },
            { 'template': '{}', 'args': [datetime.now().strftime('%d %b, %H:%M:%S')], 'action': lambda: self.__set_active_view('menu') }
        ]


    def __menu_content(self):
        return [ 
            { 'template': 'Camera', 'args': [], 'action': lambda: self.__set_active_view('camera') },
            { 'template': 'Alarms', 'args': [], 'action': lambda: self.__set_active_view('alarms') },
            { 'template': 'System stats', 'args': [], 'action': lambda: self.__set_active_view('stats') },
            { 'template': 'BLE climate', 'args': [], 'action': lambda: self.__set_active_view('ble_climate') },
            { 'template': '    <-', 'args': [], 'action': lambda: self.__set_active_view('hello') }
        ]


    def __camera_content(self):
        return [
            { 
                'template': 'Vertical: {}', 
                'args': [self.__servos_controller.vertical_servo_angle],
                'action': lambda: self.__set_scroll_alternative_function('vertical')
            },
            { 
                'template': 'Horizontal: {}',
                'args': [self.__servos_controller.horizontal_servo_angle],
                'action': lambda: self.__set_scroll_alternative_function('horizontal')
            },
            { 'template': 'Center', 'args': [], 'action': lambda: self.__servos_controller.move('CENTER') },
            {
                'template': 'LED: {}',
                'args': [int(self.__camera_light.value * 100)],
                'action': lambda: self.__set_scroll_alternative_function('brightness')
            },
            { 'template': '    <-', 'args': [], 'action': lambda: self.__set_active_view('menu') }
        ]


    def __alarms_content(self):
        return [
            { 'template': 'Monday       {}', 'args': [self.__format_alarm_time('monday')], 'action': lambda: self.__set_active_alarm_details_view('Monday') },
            { 'template': 'Tuesday      {}', 'args': [self.__format_alarm_time('tuesday')], 'action': lambda: self.__set_active_alarm_details_view('Tuesday') },
            { 'template': 'Wednesday    {}', 'args': [self.__format_alarm_time('wednesday')], 'action': lambda: self.__set_active_alarm_details_view('Wednesday') },
            { 'template': 'Thursday     {}', 'args': [self.__format_alarm_time('thursday')], 'action': lambda: self.__set_active_alarm_details_view('Thursday') },
            { 'template': 'Friday       {}', 'args': [self.__format_alarm_time('friday')], 'action': lambda: self.__set_active_alarm_details_view('Friday') },
            { 'template': 'Saturday     {}', 'args': [self.__format_alarm_time('saturday')], 'action': lambda: self.__set_active_alarm_details_view('Saturday') },
            { 'template': 'Sunday       {}', 'args': [self.__format_alarm_time('sunday')], 'action': lambda: self.__set_active_alarm_details_view('Sunday') },
            { 'template': '    <-', 'args': [], 'action': lambda: self.__set_active_view('menu') }
        ]
    

    def __alarm_details_content(self):
        return [
            { 'template': '{}   {}', 'args': [self.__selected_alarm_day, self.__format_alarm_time(self.__selected_alarm_day)], 'action': lambda: self.__set_scroll_alternative_function('set_hour') },
            { 'template': '{}', 'args': [self.__format_alarm_enabled()], 'action': self.__toggle_alarm_enabled },
            { 'template': '{}', 'args': [self.__alarm_details_melody], 'action': lambda: self.__set_scroll_alternative_function('alarm_melody') },
            { 'template': '{}', 'args': ['Stop' if self.__melody_player.is_playing() else 'Play'], 'action': self.__play_stop_melody },
            { 'template': 'Save', 'args': [], 'action': self.__save_alarm },
            { 'template': '    <-', 'args': [], 'action': lambda: self.__set_active_view('alarms') }
        ]


    def __play_stop_melody(self):
        if self.__melody_player.is_playing():
            self.__melody_player.stop()
        else:
            self.__melody_player.play(self.__alarm_details_melody)


    def __save_alarm(self):
        self.__alarm_manager.save_day({
            'day': self.__selected_alarm_day.lower(),
            'hour': self.__alarm_details_hour,
            'minute': self.__alarm_details_minute,
            'enabled': self.__alarm_details_enabled,
            'melody': self.__alarm_details_melody
        })


    def __toggle_alarm_enabled(self):
        self.__alarm_details_enabled = not self.__alarm_details_enabled


    def __format_alarm_time(self, day: str):
        day = day.lower()
        if self.__active_view == 'alarms':
            alarm = list(filter(lambda item: item['day'] == day, self.__alarm_manager.schedule))
            if len(alarm) == 1 and alarm[0]['enabled']:
                return f"{alarm[0]['hour']:02d}:{alarm[0]['minute']:02d}"
            return "--:--"
        elif self.__active_view == 'alarm_details':
            return f"{self.__alarm_details_hour:02d}:{self.__alarm_details_minute:02d}"


    def __format_alarm_enabled(self):
        if self.__alarm_details_enabled:
            return "Enabled"
        return "Disabled"

    
    def __stats_content(self):
        return [ 
            { 'template': 'CPU: {}%', 'args': [get_cpu_percent()], 'action': lambda: self.__set_active_view('menu') },
            { 'template': 'CPU temp: {}' + chr(223) + 'C', 'args': [get_cpu_temperature()], 'action': lambda: self.__set_active_view('menu') },
            { 'template': 'RAM usage: {}%', 'args': [get_ram_usage()], 'action': lambda: self.__set_active_view('menu') }
        ]


    def __ble_climate_view_content(self):
        return [
            { 
                'template': 'Humidity: {}',
                'args': [f'{self.__ble_manager.humidity}%' if self.__ble_manager.humidity is not None else '-'],
                'action': lambda: self.__set_active_view('menu')
            },
            { 
                'template': 'Temperature: {}',
                'args': [f'{self.__ble_manager.temperature}{chr(223)}C' if self.__ble_manager.temperature is not None else '-'],
                'action': lambda: self.__set_active_view('menu')
            },
            {
                'template': 'Voltage: {}',
                'args': [f'{self.__ble_manager.voltage}V' if self.__ble_manager.voltage is not None else '-'],
                'action': lambda: self.__set_active_view('menu')
            },
            {
                'template': 'Updated: {}',
                'args': [self.__ble_manager.last_updated.strftime('%H:%M:%S') if self.__ble_manager.last_updated is not None else '-'],
                'action': lambda: self.__set_active_view('menu')
            }
        ]

    
    def __get_items_count(self):
        if self.__active_view == 'menu':
            return 5
        if self.__active_view == 'camera':
            return 5
        elif self.__active_view == 'alarm_details':
            return 6
        elif self.__active_view == 'alarms':
            return 8


    def __set_active_view(self, view: str):
        self.__active_view = view
    

    def __set_active_alarm_details_view(self, day: str):
        alarm = list(filter(lambda item: item['day'] == day.lower(), self.__alarm_manager.schedule))
        self.__alarm_details_hour = alarm[0]['hour']
        self.__alarm_details_minute = alarm[0]['minute']
        self.__selected_alarm_day = day
        self.__alarm_details_enabled = alarm[0]['enabled']
        self.__alarm_details_melody = alarm[0]['melody']
        self.__set_active_view('alarm_details')

    
    def __set_scroll_alternative_function(self, func: str|None):
        self.__encoder_button.when_pressed = None
        sleep(0.2)
        self.__scroll_alternative_function = func
        if func == 'set_hour':
            self.__encoder_button.when_pressed = lambda: self.__set_scroll_alternative_function('set_minute')
        elif func is not None:
            self.__encoder_button.when_pressed = lambda: self.__set_scroll_alternative_function(None)
