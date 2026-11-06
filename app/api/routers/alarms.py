from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool

from app.api.errors import bad_request
from app.api.request_body import read_json_body
from app.api.security import current_user
from app.config import ALARMS_FILE
from app.json_store import read_json, write_json
from app.services import get_services
from app.validation import valid_melody, validate_alarms

router = APIRouter(prefix='/alarms', dependencies=[Depends(current_user)])


@router.get('')
def get_alarms():
    return read_json(ALARMS_FILE)


@router.post('', status_code=201)
async def set_alarms(request: Request):
    data = await read_json_body(request)
    error = validate_alarms(data)
    if error:
        raise bad_request(error)

    def save():
        write_json(ALARMS_FILE, data)
        # Without this the running scheduler keeps the old schedule until the server is restarted
        get_services().alarm_manager.reload()

    await run_in_threadpool(save)
    return Response(status_code=201)


@router.post('/play')
async def play(request: Request):
    data = await read_json_body(request)
    if not valid_melody(data):
        raise bad_request('Unknown melody')

    get_services().melody_player.play(data['melody'])
    return Response(status_code=204)
