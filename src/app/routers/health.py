from fastapi import APIRouter
from sqlalchemy import text

from app.core.deps import SessionDep
from app.schemas.health import HealthInfo
from app.schemas.response import ApiResponse

router = APIRouter()


@router.get("/healthz", response_model=ApiResponse[HealthInfo])
async def healthz(session: SessionDep) -> ApiResponse[HealthInfo]:
    db_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"
    return ApiResponse[HealthInfo](data=HealthInfo(status="ok", db=db_status))
