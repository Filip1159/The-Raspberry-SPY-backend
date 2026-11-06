import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.config import REFRESH_TOKEN_DAYS, REFRESH_TOKENS_FILE
from app.json_store import read_json, update_json, write_json

# A spent token keeps working this long, so two browser tabs refreshing at the same moment both succeed
GRACE_SECONDS = 30


def _digest(token: str) -> str:
    # Only hashes are stored: a leaked file does not contain usable tokens
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> float:
    return datetime.now(UTC).timestamp()


def _load() -> dict:
    try:
        return read_json(REFRESH_TOKENS_FILE)
    except FileNotFoundError:
        write_json(REFRESH_TOKENS_FILE, {})
        return {}


def _alive(entries: dict) -> dict:
    now = _now()
    return {digest: entry for digest, entry in entries.items() if entry['expires'] > now}


def issue(username: str) -> str:
    """Creates a refresh token for the user and remembers it"""
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_DAYS)).timestamp()
    _load()
    update_json(REFRESH_TOKENS_FILE, lambda entries: {**_alive(entries), _digest(token): {'username': username, 'expires': expires}})
    return token


def rotate(token: str) -> tuple[str, str] | None:
    """Spends a refresh token: returns (username, new token), or None when the token is unknown or expired.
    A token is meant to work once; it stays valid for GRACE_SECONDS more (tabs refreshing together), then a stolen copy is useless."""
    entry = _alive(_load()).get(_digest(token))
    if entry is None:
        return None

    cutoff = _now() + GRACE_SECONDS

    def shorten(entries: dict) -> dict:
        current = entries.get(_digest(token))
        if current is not None:
            current['expires'] = min(current['expires'], cutoff)
        return _alive(entries)

    update_json(REFRESH_TOKENS_FILE, shorten)
    return entry['username'], issue(entry['username'])


def revoke_all(username: str) -> int:
    """Signs the user out everywhere (a changed password must not leave old sessions alive); returns how many were revoked"""
    _load()
    removed = []

    def drop(entries: dict) -> dict:
        kept = {digest: entry for digest, entry in _alive(entries).items() if entry['username'] != username}
        removed.append(len(entries) - len(kept))
        return kept

    update_json(REFRESH_TOKENS_FILE, drop)
    return removed[0]


def revoke(token: str) -> None:
    _load()
    update_json(
        REFRESH_TOKENS_FILE, lambda entries: {digest: entry for digest, entry in _alive(entries).items() if digest != _digest(token)}
    )
