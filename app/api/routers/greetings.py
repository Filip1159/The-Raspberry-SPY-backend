from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool

from app.api.errors import bad_request
from app.api.rate_limit import greetings_limit
from app.api.request_body import read_json_body
from app.api.security import current_user
from app.config import GREETINGS_FILE
from app.json_store import read_json, update_json
from app.validation import validate_greeting

router = APIRouter(prefix='/greetings')

MAX_STORED_GREETINGS = 1000  # the oldest ones are dropped, so the public endpoint cannot fill the disk


# Public, but limited per visitor; invalid requests count too
@router.post('', status_code=201)
async def publish_greeting(request: Request):
    greetings_limit.limit_and_count(request)

    data = await read_json_body(request)
    error = validate_greeting(data)
    if error:
        raise bad_request(error)

    entry = {'text': data['text'].strip(), 'timestamp': datetime.now().isoformat()}
    await run_in_threadpool(update_json, GREETINGS_FILE, lambda current: (current + [entry])[-MAX_STORED_GREETINGS:])
    return Response(status_code=201)


# Greetings are meant for the owner only
@router.get('', dependencies=[Depends(current_user)])
def get_greetings():
    return read_json(GREETINGS_FILE)
