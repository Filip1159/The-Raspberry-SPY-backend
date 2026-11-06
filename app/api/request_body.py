from fastapi import Request


async def read_json_body(request: Request):
    """The parsed JSON body, or None when it is missing or not valid JSON (like Flask's get_json(silent=True))"""
    try:
        return await request.json()
    except ValueError:
        return None
