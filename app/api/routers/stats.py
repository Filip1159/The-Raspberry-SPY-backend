from fastapi import APIRouter, Depends

from app.api.security import current_user
from app.stats_history import stats_history

router = APIRouter(prefix='/stats', dependencies=[Depends(current_user)])


@router.get('/history')
def get_history():
    return stats_history.samples()
