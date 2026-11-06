from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from app.allowed_origins import ALLOWED_ORIGINS
from app.config import KEY_PUBLIC_PATH, PORT, RATE_LIMITS_ENABLED, USERS_FILE
from app.controller.alarms_controller import alarms
from app.controller.auth_controller import auth
from app.controller.greetings_controller import greetings
from app.controller.health_controller import health
from app.controller.socket_controller import socketio
from app.rate_limit import limiter
from app.users import migrate_plaintext_passwords

app = Flask('rpi_server')
app.config['JWT_ALGORITHM'] = 'RS256'
app.config['JWT_PUBLIC_KEY'] = open(KEY_PUBLIC_PATH).read()
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024  # the API only receives small JSON bodies
app.config['RATELIMIT_ENABLED'] = RATE_LIMITS_ENABLED
jwt_manager = JWTManager(app)
CORS(app, origins=ALLOWED_ORIGINS)
limiter.init_app(app)
migrate_plaintext_passwords(USERS_FILE)


@app.errorhandler(429)
def too_many_requests(_):
    return jsonify({'error': 'Too many requests, please try again later'}), 429


app.register_blueprint(alarms)
app.register_blueprint(auth)
app.register_blueprint(greetings)
app.register_blueprint(health)
socketio.init_app(app)


def run_server():
    socketio.run(
        app, host='0.0.0.0', port=PORT, allow_unsafe_werkzeug=True
    )  # DO NOT USE debug=True https://stackoverflow.com/questions/77707533/busy-gpios-raspberry-pi5
