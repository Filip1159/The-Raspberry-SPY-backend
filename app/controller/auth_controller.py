import json
from datetime import UTC, datetime, timedelta

import jwt
from flask import Blueprint, jsonify, request
from jwcrypto import jwk

from app.config import USERS_FILE
from app.rate_limit import limiter
from app.secret_provider import get_keys
from app.users import verify_credentials

auth = Blueprint('auth', __name__)

private_pem, public_pem = get_keys()

public_key_jwk = jwk.JWK.from_pem(public_pem)
public_jwk_json = json.loads(public_key_jwk.export_public())
kid = public_jwk_json['kid']


@auth.route('/.well-known/jwks.json')
def jwks():
    return jsonify({'keys': [public_jwk_json]})


# Only failed attempts count towards the limit, so legitimate logins are never blocked
@auth.route('/login', methods=['POST'])
@limiter.limit('5 per minute;20 per hour', deduct_when=lambda response: response.status_code == 401)
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    if not verify_credentials(USERS_FILE, data.get('username'), data.get('password')):
        return jsonify({'msg': 'bad credentials'}), 401

    return prepare_token(data['username'])


def prepare_token(username):
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=30)

    permissions = [{'action': 'publish', 'path': 'cam1'}, {'action': 'read', 'path': 'cam1'}]

    payload = {'sub': username, 'iat': int(now.timestamp()), 'exp': int(exp.timestamp()), 'mediamtx_permissions': permissions}

    headers = {'kid': kid, 'alg': 'RS256', 'typ': 'JWT'}

    token = jwt.encode(payload, private_pem, algorithm='RS256', headers=headers)

    return jsonify({'access_token': token, 'expires_at': exp.isoformat()})
