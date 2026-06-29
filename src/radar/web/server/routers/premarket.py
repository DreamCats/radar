from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, time
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from radar.core.config import RadarConfig
from radar.core.messages import load_catalyst_terms
from radar.core.storage import connect_readonly
from radar.core.usecases.catalyst_stocks import load_catalyst_stock_detector
from radar.core.usecases.premarket_signal import (
    PremarketSignalQuery,
    PremarketSignalResult,
    build_premarket_signal,
)
from radar.web.server.deps import get_config
from radar.web.server.read_through import request_cache_key, request_operation

T = TypeVar("T")

router = APIRouter(prefix="/api", tags=["premarket"])


@router.get("/premarket/signals", response_model=PremarketSignalResult)
def premarket_signals(
    request: Request,
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    config: RadarConfig = Depends(get_config),
) -> PremarketSignalResult:
    resolved_start, resolved_end = _resolve_window(start_time, end_time)
    if resolved_end <= resolved_start:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")

    query = PremarketSignalQuery(start_time=resolved_start, end_time=resolved_end, limit=limit)

    def compute() -> PremarketSignalResult:
        message_conn = connect_readonly(config.database_path)
        market_conn = _connect_optional(config.market_database_path)
        try:
            return build_premarket_signal(
                message_conn,
                market_conn=market_conn,
                library=load_catalyst_terms(config),
                query=query,
                stock_detector=load_catalyst_stock_detector(config),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            message_conn.close()
            if market_conn is not None:
                market_conn.close()

    return _cached_read(request, config, group="heavy", ttl_seconds=15.0, compute=compute)


def _resolve_window(
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[datetime, datetime]:
    base_date = (start_time or end_time or datetime.now()).date()
    return (
        start_time or datetime.combine(base_date, time(hour=7)),
        end_time or datetime.combine(base_date, time(hour=9, minute=25)),
    )


def _connect_optional(database_path) -> sqlite3.Connection | None:
    if not database_path.exists():
        return None
    try:
        return connect_readonly(database_path)
    except sqlite3.OperationalError as exc:
        if "unable to open database file" not in str(exc).lower():
            raise
        return None


def _cached_read(
    request: Request,
    config: RadarConfig,
    *,
    group: str,
    ttl_seconds: float,
    compute: Callable[[], T],
) -> T:
    scope = f"{config.database_path}:{config.market_database_path}:{config.config_dir}"
    return request.app.state.read_coordinator.get_or_compute(
        key=request_cache_key(request, scope=scope),
        operation=request_operation(request),
        group=group,
        ttl_seconds=ttl_seconds,
        compute=compute,
    )
