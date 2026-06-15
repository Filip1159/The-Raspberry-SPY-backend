import json
from datetime import datetime

from flask import Blueprint, jsonify, request

greetings = Blueprint('greetings', __name__, url_prefix='/greetings')

GREETINGS_FILE = './resources/greetings.json'


@greetings.route('', methods=['POST'])
def publish_greeting():
    data = request.get_json()
    text = data.get('text')

    if not isinstance(text, str) or len(text) == 0:
        return jsonify({'error': 'Invalid greeting text'}), 400

    with open(GREETINGS_FILE, 'r+', encoding='utf-8') as file:
        current_content = json.loads(file.read())
        current_content.append({'text': text, 'timestamp': datetime.now().isoformat()})
        file.seek(0)
        json.dump(current_content, file, ensure_ascii=False, indent=2)

    return '', 201


@greetings.route('', methods=['GET'])
def get_greetings():
    with open(GREETINGS_FILE, encoding='utf-8') as file:
        return file.read(), 200
