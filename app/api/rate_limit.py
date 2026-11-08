import time

from fastapi import Request
from limits import parse_many
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.api.errors import ApiError
from app.config import RATE_LIMITS_ENABLED

# In-memory counters: enough for a single process (they reset on restart)
_limiter = FixedWindowRateLimiter(MemoryStorage())


def client_ip(request: Request) -> str:
    """The real visitor address: the app sits behind nginx and a Cloudflare Tunnel, so the peer is always localhost.

    CF-Connecting-IP is set by Cloudflare; the header could be forged by someone who reaches nginx/uvicorn directly on the
    home network, which only lets them dodge their own limit.
    """
    return request.headers.get('CF-Connecting-IP') or (request.client.host if request.client else 'unknown')


class RateLimit:
    """Limits such as '5 per minute;20 per hour' per visitor and endpoint.

    `check(request)` answers 429 when a limit is used up, `hit(request)` counts one request. Endpoints that should only
    count failures (the login) call `hit` themselves; the others use `limit_and_count`.
    """

    def __init__(self, name: str, spec: str):
        self.name = name
        self.items = parse_many(spec)

    def _key(self, request: Request) -> str:
        return f'{self.name}:{client_ip(request)}'

    def check(self, request: Request) -> None:
        if not RATE_LIMITS_ENABLED:
            return
        key = self._key(request)
        for item in self.items:
            if not _limiter.test(item, key):
                retry_after = max(1, int(_limiter.get_window_stats(item, key).reset_time - time.time()) + 1)
                raise ApiError(429, {'error': 'Too many requests, please try again later'}, {'Retry-After': str(retry_after)})

    def hit(self, request: Request) -> None:
        if RATE_LIMITS_ENABLED:
            for item in self.items:
                _limiter.hit(item, self._key(request))

    def limit_and_count(self, request: Request) -> None:
        self.check(request)
        self.hit(request)


login_limit = RateLimit('login', '5 per minute;20 per hour')
greetings_limit = RateLimit('greetings', '3 per minute;20 per hour')
# The UI refreshes once per ~30 minutes per tab; this only stops somebody hammering the endpoint with guessed cookies
refresh_limit = RateLimit('refresh', '30 per minute')
# Every change restarts the camera stream for a few seconds
camera_limit = RateLimit('camera', '10 per minute')
# One renewal every ~70 s per open stream; this only stops somebody hammering the endpoint
stream_token_limit = RateLimit('stream-token', '20 per minute')
