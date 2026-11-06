import jwt
from fastapi import Request

from app.api.errors import ApiError
from app.secret_provider import get_keys

private_pem, public_pem = get_keys()


def decode_token(token: str) -> dict:
    """Verifies signature (RS256, public key) and expiry. Raises jwt.PyJWTError."""
    return jwt.decode(token, public_pem, algorithms=['RS256'], options={'require': ['exp']})


def current_user(request: Request) -> dict:
    """Dependency for the endpoints that need a signed-in user; returns the token claims"""
    header = request.headers.get('Authorization', '')
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise ApiError(401, {'msg': 'Missing Authorization Header'})
    try:
        return decode_token(token.strip())
    except jwt.ExpiredSignatureError:
        raise ApiError(401, {'msg': 'Token has expired'}) from None
    except jwt.PyJWTError:
        raise ApiError(401, {'msg': 'Invalid token'}) from None
