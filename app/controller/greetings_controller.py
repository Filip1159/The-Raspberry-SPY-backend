from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.config import GREETINGS_FILE
from app.json_store import read_json, update_json
from app.rate_limit import limiter
from app.validation import MAX_GREETING_LENGTH, validate_greeting  # noqa: F401 (re-exported for the tests)

greetings = Blueprint('greetings', __name__, url_prefix='/greetings')

MAX_STORED_GREETINGS = 1000  # the oldest ones are dropped, so the public endpoint cannot fill the disk


@greetings.route('', methods=['POST'])
@limiter.limit('3 per minute;20 per hour')
def publish_greeting():
    data = request.get_json(silent=True)

    error = validate_greeting(data)
    if error:
        return jsonify({'error': error}), 400

    entry = {'text': data['text'].strip(), 'timestamp': datetime.now().isoformat()}
    update_json(GREETINGS_FILE, lambda current: (current + [entry])[-MAX_STORED_GREETINGS:])

    return '', 201


# Greetings are meant for the owner only
@greetings.route('', methods=['GET'])
@jwt_required()
def get_greetings():
    return jsonify(read_json(GREETINGS_FILE))
