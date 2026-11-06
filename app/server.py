from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from app.allowed_origins import ALLOWED_ORIGINS
from app.controller.alarms_controller import alarms
from app.controller.auth_controller import auth
from app.controller.greetings_controller import greetings
from app.controller.health_controller import health
from app.controller.socket_controller import socketio
from app.secret_provider import KEY_PUBLIC_PATH

app = Flask('rpi_server')
app.config['JWT_ALGORITHM'] = 'RS256'
app.config['JWT_PUBLIC_KEY'] = open(KEY_PUBLIC_PATH).read()
jwt_manager = JWTManager(app)
CORS(app, origins=ALLOWED_ORIGINS)

app.register_blueprint(alarms)
app.register_blueprint(auth)
app.register_blueprint(greetings)
app.register_blueprint(health)
socketio.init_app(app)


def run_server():
    socketio.run(
        app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True
    )  # DO NOT USE debug=True https://stackoverflow.com/questions/77707533/busy-gpios-raspberry-pi5
