import json
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from jwcrypto import jwk

from app.api.errors import ApiError
from app.api.rate_limit import login_limit
from app.api.request_body import read_json_body
from app.api.security import private_pem, public_pem
from app.config import USERS_FILE
from app.users import verify_credentials

router = APIRouter()

public_jwk = json.loads(jwk.JWK.from_pem(public_pem).export_public())
kid = public_jwk['kid']


@router.get('/.well-known/jwks.json')
def jwks():
    return {'keys': [public_jwk]}


# Only failed attempts count towards the limit, so legitimate logins are never blocked
@router.post('/login')
async def login(request: Request):
    login_limit.check(request)

    data = await read_json_body(request)
    if not isinstance(data, dict):
        data = {}

    # scrypt takes ~100 ms of CPU: keep it off the event loop
    if not await run_in_threadpool(verify_credentials, USERS_FILE, data.get('username'), data.get('password')):
        login_limit.hit(request)
        raise ApiError(401, {'msg': 'bad credentials'})

    return prepare_token(data['username'])


def prepare_token(username: str) -> dict:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=30)
    permissions = [{'action': 'publish', 'path': 'cam1'}, {'action': 'read', 'path': 'cam1'}]
    payload = {'sub': username, 'iat': int(now.timestamp()), 'exp': int(exp.timestamp()), 'mediamtx_permissions': permissions}
    headers = {'kid': kid, 'alg': 'RS256', 'typ': 'JWT'}
    token = jwt.encode(payload, private_pem, algorithm='RS256', headers=headers)
    return {'access_token': token, 'expires_at': exp.isoformat()}
