from flask import Blueprint, jsonify

health = Blueprint('health', __name__)


@health.route('/health')
def get_health():
    return jsonify({'status': 'ok'})
