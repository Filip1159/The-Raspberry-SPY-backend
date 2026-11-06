from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.alarm_manager import alarm_manager
from app.config import ALARMS_FILE
from app.json_store import read_json, write_json
from app.validation import valid_melody, validate_alarms

alarms = Blueprint('alarms', __name__, url_prefix='/alarms')


@alarms.route('', methods=['POST'])
@jwt_required()
def set_alarms():
    data = request.get_json(silent=True)

    error = validate_alarms(data)
    if error:
        return jsonify({'error': error}), 400

    write_json(ALARMS_FILE, data)
    # Without this the running scheduler keeps the old schedule until Flask is restarted
    alarm_manager.reload()

    return '', 201


@alarms.route('', methods=['GET'])
@jwt_required()
def get_alarms():
    return jsonify(read_json(ALARMS_FILE))


@alarms.route('/play', methods=['POST'])
@jwt_required()
def play():
    data = request.get_json(silent=True)
    if not valid_melody(data):
        return jsonify({'error': 'Unknown melody'}), 400

    alarm_manager.player.play(data['melody'])
    return '', 204
