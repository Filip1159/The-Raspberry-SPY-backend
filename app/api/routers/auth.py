import json
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from jwcrypto import jwk

from app import refresh_tokens
from app.api.errors import ApiError
from app.api.rate_limit import login_limit, refresh_limit
from app.api.request_body import read_json_body
from app.api.security import private_pem, public_pem
from app.config import COOKIE_SECURE, REFRESH_TOKEN_DAYS, USERS_FILE
from app.users import load_users, verify_credentials

REFRESH_COOKIE = 'refresh_token'

router = APIRouter()

public_jwk = json.loads(jwk.JWK.from_pem(public_pem).export_public())
kid = public_jwk['kid']


@router.get('/.well-known/jwks.json')
def jwks():
    return {'keys': [public_jwk]}


# Only failed attempts count towards the limit, so legitimate logins are never blocked
@router.post('/login')
async def login(request: Request, response: Response):
    login_limit.check(request)

    data = await read_json_body(request)
    if not isinstance(data, dict):
        data = {}

    # scrypt takes ~100 ms of CPU: keep it off the event loop
    if not await run_in_threadpool(verify_credentials, USERS_FILE, data.get('username'), data.get('password')):
        login_limit.hit(request)
        raise ApiError(401, {'msg': 'bad credentials'})

    username = data['username']
    set_refresh_cookie(response, await run_in_threadpool(refresh_tokens.issue, username))
    return prepare_token(username)


@router.post('/refresh')
async def refresh(request: Request, response: Response):
    """Trades the refresh cookie for a new access token (and a new refresh cookie)"""
    refresh_limit.limit_and_count(request)
    spent = await run_in_threadpool(refresh_tokens.rotate, request.cookies.get(REFRESH_COOKIE, ''))
    # A user that has been removed since the login must not get new tokens
    users = await run_in_threadpool(load_users, USERS_FILE)
    if spent is None or spent[0] not in {user['username'] for user in users}:
        raise ApiError(401, {'msg': 'No valid refresh token'}, headers=cookie_clearing_header())

    username, new_token = spent
    set_refresh_cookie(response, new_token)
    return prepare_token(username)


@router.post('/logout', status_code=204)
async def logout(request: Request, response: Response):
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        await run_in_threadpool(refresh_tokens.revoke, token)
    response.delete_cookie(REFRESH_COOKIE, path='/')
    response.status_code = 204
    return None


def set_refresh_cookie(response: Response, token: str) -> None:
    # SameSite=Strict is enough: the UI (filipwisniewski.pl) and the API (api.filipwisniewski.pl) are the same site
    response.set_cookie(
        REFRESH_COOKIE, token, max_age=REFRESH_TOKEN_DAYS * 24 * 3600, httponly=True, secure=COOKIE_SECURE, samesite='strict', path='/'
    )


def cookie_clearing_header() -> dict[str, str]:
    secure = '; Secure' if COOKIE_SECURE else ''
    return {'Set-Cookie': f'{REFRESH_COOKIE}=""; Max-Age=0; Path=/; HttpOnly; SameSite=strict{secure}'}


def prepare_token(username: str) -> dict:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=30)
    permissions = [{'action': 'publish', 'path': 'cam1'}, {'action': 'read', 'path': 'cam1'}]
    payload = {'sub': username, 'iat': int(now.timestamp()), 'exp': int(exp.timestamp()), 'mediamtx_permissions': permissions}
    headers = {'kid': kid, 'alg': 'RS256', 'typ': 'JWT'}
    token = jwt.encode(payload, private_pem, algorithm='RS256', headers=headers)
    return {'access_token': token, 'expires_at': exp.isoformat()}
