"""Request validation for the REST API: plain functions returning the error message the frontend expects (400, not FastAPI's 422)"""

from app.melody_player import MELODIES

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
MAX_GREETING_LENGTH = 500


def validate_alarms(data) -> str | None:
    """Returns the error message for an invalid alarm list, or None when it is fine"""
    if not isinstance(data, list):
        return 'Body must be a list'

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            return f'Item at index {index} is not an object'

        hour = item.get('hour')
        minute = item.get('minute')
        melody = item.get('melody')

        if item.get('day') not in DAYS:
            return f'Invalid day at index {index}'
        if not isinstance(hour, int) or isinstance(hour, bool) or not (0 <= hour <= 23):
            return f'Invalid hour at index {index}'
        if not isinstance(minute, int) or isinstance(minute, bool) or not (0 <= minute <= 59):
            return f'Invalid minute at index {index}'
        if melody not in MELODIES:
            return f'Invalid melody at index {index}: {melody}'
        if not isinstance(item.get('enabled'), bool):
            return f'Invalid enabled value at index {index}'
    return None


def validate_greeting(data) -> str | None:
    text = data.get('text') if isinstance(data, dict) else None
    if not isinstance(text, str) or not text.strip():
        return 'Invalid greeting text'
    if len(text) > MAX_GREETING_LENGTH:
        return f'Greeting is too long (max {MAX_GREETING_LENGTH} characters)'
    return None


def valid_melody(data) -> bool:
    melody = data.get('melody') if isinstance(data, dict) else None
    return isinstance(melody, str) and melody in MELODIES
