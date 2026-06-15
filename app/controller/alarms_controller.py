import json

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.alarm_manager import ALARMS_FILE, alarm_manager
from app.melody_player import MELODIES

alarms = Blueprint('alarms', __name__, url_prefix='/alarms')


@alarms.route('', methods=['POST'])
@jwt_required()
def set_alarms():
    data = request.get_json()

    if not isinstance(data, list):
        return jsonify({'error': 'Body must be a list'}), 400

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            return jsonify({'error': f'Item at index {index} is not an object'}), 400

        day = item.get('day')
        hour = item.get('hour')
        minute = item.get('minute')
        melody = item.get('melody')
        enabled = item.get('enabled')

        if day not in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            return jsonify({'error': f'Invalid day at index {index}'}), 400

        if not isinstance(hour, int) or not (0 <= hour <= 23):
            return jsonify({'error': f'Invalid hour at index {index}'}), 400

        if not isinstance(minute, int) or not (0 <= minute <= 59):
            return jsonify({'error': f'Invalid minute at index {index}'}), 400

        if melody not in MELODIES.keys():
            return jsonify({'error': f'Invalid melody at index {index}: {melody}'}), 400

        if not isinstance(enabled, bool):
            return jsonify({'error': f'Invalid enabled value at index {index}'}), 400

    with open(ALARMS_FILE, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    return '', 201


@alarms.route('', methods=['GET'])
@jwt_required()
def get_alarms():
    with open(ALARMS_FILE, encoding='utf-8') as file:
        return file.read(), 200


@alarms.route('/play', methods=['POST'])
@jwt_required()
def play():
    data = request.get_json()
    melody = data.get('melody')
    alarm_manager.player.play(melody)
    return '', 204
