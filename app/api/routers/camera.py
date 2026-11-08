from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from app.api.errors import bad_request
from app.api.rate_limit import camera_limit
from app.api.request_body import read_json_body
from app.api.security import current_user
from app.camera_settings import DEFAULTS, validate_camera_settings
from app.services import get_services

router = APIRouter(prefix='/camera', dependencies=[Depends(current_user)])


def _view(settings: dict, applied: bool) -> dict:
    """`applied`: the running stream uses these settings (false while MediaMTX is down; the backend keeps retrying)"""
    return {'settings': settings, 'defaults': DEFAULTS, 'applied': applied}


@router.get('/settings')
async def get_settings():
    camera_settings = get_services().camera_settings

    def read():
        settings = camera_settings.get()
        return _view(settings, camera_settings.is_applied(settings))

    return await run_in_threadpool(read)


@router.put('/settings')
async def set_settings(request: Request):
    camera_limit.limit_and_count(request)

    data = await read_json_body(request)
    error = validate_camera_settings(data)
    if error:
        raise bad_request(error)

    camera_settings = get_services().camera_settings

    def save():
        camera_settings.save(data)
        return _view(data, camera_settings.apply(data))

    return await run_in_threadpool(save)
