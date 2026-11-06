from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """An error with the JSON body the frontend expects: {'error': ...} (400, 429) or {'msg': ...} (401)"""

    def __init__(self, status_code: int, body: dict, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}


def bad_request(message: str) -> ApiError:
    return ApiError(400, {'error': message})


async def api_error_handler(_: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(error.body, status_code=error.status_code, headers=error.headers)
