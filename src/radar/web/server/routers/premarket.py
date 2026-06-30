from __future__ import annotations

import gzip
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from radar.core.config import RadarConfig
from radar.core.messages import load_catalyst_terms
from radar.core.storage import connect_readonly
from radar.core.usecases.catalyst_stocks import load_catalyst_stock_detector
from radar.core.usecases.premarket_signal import (
    PremarketConceptRank,
    PremarketSignalQuery,
    PremarketSignalResult,
    build_premarket_signal,
    find_premarket_concept,
    slim_premarket_signal,
)
from radar.web.server.deps import get_config
from radar.web.server.read_through import request_operation

_PREMARKET_CACHE_TTL_SECONDS = 15.0

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
    return slim_premarket_signal(_cached_premarket_payload(request, config, query).result)


@router.get("/premarket/signals/full")
def premarket_signals_full(
    request: Request,
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    config: RadarConfig = Depends(get_config),
) -> Response:
    resolved_start, resolved_end = _resolve_window(start_time, end_time)
    if resolved_end <= resolved_start:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")

    query = PremarketSignalQuery(start_time=resolved_start, end_time=resolved_end, limit=limit)
    payload = _cached_premarket_payload(request, config, query)
    return _premarket_json_response(request, payload)


@router.get("/premarket/signals/concepts/{concept_code}", response_model=PremarketConceptRank)
def premarket_signal_concept(
    concept_code: str,
    request: Request,
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    config: RadarConfig = Depends(get_config),
) -> PremarketConceptRank:
    resolved_start, resolved_end = _resolve_window(start_time, end_time)
    if resolved_end <= resolved_start:
        raise HTTPException(status_code=400, detail="end_time 必须晚于 start_time")

    query = PremarketSignalQuery(start_time=resolved_start, end_time=resolved_end, limit=limit)
    concept = find_premarket_concept(_cached_premarket_payload(request, config, query).result, concept_code)
    if concept is None:
        raise HTTPException(status_code=404, detail="未找到概念")
    return concept


@dataclass(frozen=True)
class _PremarketPayload:
    result: PremarketSignalResult
    json_bytes: bytes
    gzip_bytes: bytes
    etag: str


def _cached_premarket_payload(
    request: Request,
    config: RadarConfig,
    query: PremarketSignalQuery,
) -> _PremarketPayload:
    def compute() -> _PremarketPayload:
        message_conn = connect_readonly(config.database_path)
        market_conn = _connect_optional(config.market_database_path)
        try:
            result = build_premarket_signal(
                message_conn,
                market_conn=market_conn,
                library=load_catalyst_terms(config),
                query=query,
                stock_detector=load_catalyst_stock_detector(config),
            )
            json_bytes = result.model_dump_json().encode("utf-8")
            return _PremarketPayload(
                result=result,
                json_bytes=json_bytes,
                gzip_bytes=gzip.compress(json_bytes, compresslevel=6, mtime=0),
                etag=_etag(json_bytes),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            message_conn.close()
            if market_conn is not None:
                market_conn.close()

    scope = f"{config.database_path}:{config.market_database_path}:{config.config_dir}"
    key = (
        f"{scope}:premarket_signal:{query.start_time.isoformat()}:"
        f"{query.end_time.isoformat()}:limit={query.limit}"
    )
    return request.app.state.read_coordinator.get_or_compute(
        key=key,
        operation=request_operation(request),
        group="heavy",
        ttl_seconds=_PREMARKET_CACHE_TTL_SECONDS,
        compute=compute,
    )


def _premarket_json_response(request: Request, payload: _PremarketPayload) -> Response:
    headers = {
        "Cache-Control": f"private, max-age={int(_PREMARKET_CACHE_TTL_SECONDS)}",
        "ETag": payload.etag,
        "Vary": "Accept-Encoding",
    }
    if request.headers.get("if-none-match") == payload.etag:
        return Response(status_code=304, headers=headers)
    if _accepts_gzip(request):
        headers["Content-Encoding"] = "gzip"
        return Response(content=payload.gzip_bytes, media_type="application/json", headers=headers)
    return Response(content=payload.json_bytes, media_type="application/json", headers=headers)


def _accepts_gzip(request: Request) -> bool:
    accept_encoding = request.headers.get("accept-encoding", "")
    return "gzip" in accept_encoding.lower() and "gzip;q=0" not in accept_encoding.lower()


def _etag(data: bytes) -> str:
    return f'W/"{hashlib.sha256(data).hexdigest()[:16]}"'


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
