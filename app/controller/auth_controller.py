from datetime import datetime, timedelta, UTC
from flask import Blueprint, jsonify, request
import json
import jwt
from jwcrypto import jwk

from app.secret_provider import get_keys


USERS_JSON_PATH = "/home/fwisn/Documents/camera-app/resources/users.json"


auth = Blueprint("auth", __name__)

private_pem, public_pem = get_keys()

public_key_jwk = jwk.JWK.from_pem(public_pem)
public_jwk_json = json.loads(public_key_jwk.export_public())
kid = public_jwk_json["kid"]


@auth.route("/.well-known/jwks.json")
def jwks():
    return jsonify({"keys": [public_jwk_json]})


@auth.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    with open(USERS_JSON_PATH, "r") as f:
        users = json.load(f)
        matching_users = list(filter(lambda u: u['username'] == username and u['password'] == password, users))

        if len(matching_users) == 0:
            return jsonify({"msg": "bad credentials"}), 401

        return prepare_token(username)


def prepare_token(username):
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=30)

    permissions = [
        {"action": "publish", "path": "cam1"},
        {"action": "read", "path": "cam1"}
    ]

    payload = {
        "sub": username,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "mediamtx_permissions": permissions
    }

    headers = {
        "kid": kid,
        "alg": "RS256",
        "typ": "JWT"
    }

    token = jwt.encode(payload, private_pem, algorithm="RS256", headers=headers)

    return jsonify({
        "access_token": token,
        "expires_at": exp.isoformat()
    })
