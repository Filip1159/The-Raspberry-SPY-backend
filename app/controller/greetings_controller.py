from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.config import GREETINGS_FILE
from app.json_store import read_json, update_json
from app.rate_limit import limiter

greetings = Blueprint('greetings', __name__, url_prefix='/greetings')

MAX_GREETING_LENGTH = 500
MAX_STORED_GREETINGS = 1000  # the oldest ones are dropped, so the public endpoint cannot fill the disk


@greetings.route('', methods=['POST'])
@limiter.limit('3 per minute;20 per hour')
def publish_greeting():
    data = request.get_json(silent=True)
    text = data.get('text') if isinstance(data, dict) else None

    if not isinstance(text, str) or not text.strip():
        return jsonify({'error': 'Invalid greeting text'}), 400
    if len(text) > MAX_GREETING_LENGTH:
        return jsonify({'error': f'Greeting is too long (max {MAX_GREETING_LENGTH} characters)'}), 400

    entry = {'text': text.strip(), 'timestamp': datetime.now().isoformat()}
    update_json(GREETINGS_FILE, lambda current: (current + [entry])[-MAX_STORED_GREETINGS:])

    return '', 201


# Greetings are meant for the owner only
@greetings.route('', methods=['GET'])
@jwt_required()
def get_greetings():
    return jsonify(read_json(GREETINGS_FILE))
