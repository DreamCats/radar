from __future__ import annotations

from fastapi import APIRouter, Depends

from radar.core.config import RadarConfig
from radar.web.server.deps import get_config
from radar.web.server.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(config: RadarConfig = Depends(get_config)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        database=str(config.database_path),
        market_database=str(config.market_database_path),
    )

