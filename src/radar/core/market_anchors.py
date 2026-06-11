from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.tushare import call as call_tushare

AnchorType = Literal["stock", "concept", "industry", "theme"]
TushareCallFn = Callable[
    [RadarConfig, str, dict[str, Any] | None, str | list[str] | None],
    list[dict[str, Any]],
]


class MarketAnchor(BaseModel):
    anchor_id: str
    anchor_type: AnchorType
    name: str
    aliases: list[str] = Field(default_factory=list)
    source: str
    source_code: str = ""
    trade_date: str
    hot_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketAnchorMember(BaseModel):
    anchor_id: str
    ts_code: str
    stock_name: str
    reason: str | None = None
    source: str
    trade_date: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RefreshMarketAnchorsResult(BaseModel):
    trade_date: str
    anchor_count: int = 0
    member_count: int = 0
    source_counts: dict[str, int] = Field(default_factory=dict)
    failed_sources: dict[str, str] = Field(default_factory=dict)


class EnsureMarketAnchorsResult(RefreshMarketAnchorsResult):
    requested_trade_date: str | None = None
    refreshed: bool = False
    skipped_reason: str | None = None


class RefreshMarketAnchorDerivativesResult(BaseModel):
    latest_trade_date: str | None = None
    current_count: int = 0
    span_count: int = 0


def ensure_market_anchors(
    config: RadarConfig,
    *,
    trade_date: str,
    min_anchor_count: int = 100,
    force: bool = False,
    use_cache: bool = True,
    tushare_call: TushareCallFn | None = None,
) -> EnsureMarketAnchorsResult:
    """确保指定交易日已有 anchor 词库；已有足够数据时不触发 Tushare。"""

    _validate_trade_date(trade_date)
    if min_anchor_count < 1:
        raise ValueError("min_anchor_count 必须大于 0")

    existing_anchor_count, existing_member_count = _stored_counts(config, trade_date)
    if not force and existing_anchor_count >= min_anchor_count:
        return EnsureMarketAnchorsResult(
            trade_date=trade_date,
            requested_trade_date=trade_date,
            anchor_count=existing_anchor_count,
            member_count=existing_member_count,
            refreshed=False,
            skipped_reason="anchor 词库已存在",
        )

    requested_trade_date = trade_date
    trade_date = resolve_market_anchor_trade_date(
        config,
        trade_date=requested_trade_date,
        tushare_call=tushare_call,
    )
    existing_anchor_count, existing_member_count = _stored_counts(config, trade_date)
    if not force and existing_anchor_count >= min_anchor_count:
        skipped_reason = "anchor 词库已存在"
        if trade_date != requested_trade_date:
            skipped_reason = f"{requested_trade_date} 非交易日，使用最近交易日 {trade_date} 的 anchor 词库"
        return EnsureMarketAnchorsResult(
            trade_date=trade_date,
            requested_trade_date=requested_trade_date,
            anchor_count=existing_anchor_count,
            member_count=existing_member_count,
            refreshed=False,
            skipped_reason=skipped_reason,
        )

    refreshed = refresh_market_anchors(
        config,
        trade_date=trade_date,
        use_cache=use_cache,
        tushare_call=tushare_call,
    )
    anchor_count, member_count = _stored_counts(config, trade_date)
    if use_cache and anchor_count < min_anchor_count:
        refreshed = refresh_market_anchors(
            config,
            trade_date=trade_date,
            use_cache=False,
            tushare_call=tushare_call,
        )
        anchor_count, member_count = _stored_counts(config, trade_date)
    if anchor_count < min_anchor_count:
        fallback_trade_date = _latest_stored_anchor_trade_date(
            config,
            before_trade_date=trade_date,
            min_anchor_count=min_anchor_count,
        )
        if fallback_trade_date is not None:
            fallback_anchor_count, fallback_member_count = _stored_counts(config, fallback_trade_date)
            return EnsureMarketAnchorsResult(
                trade_date=fallback_trade_date,
                requested_trade_date=requested_trade_date,
                anchor_count=fallback_anchor_count,
                member_count=fallback_member_count,
                source_counts=refreshed.source_counts,
                failed_sources=refreshed.failed_sources,
                refreshed=True,
                skipped_reason=f"{trade_date} anchor 词库不足，使用最近已有交易日 {fallback_trade_date} 的 anchor 词库",
            )
    return EnsureMarketAnchorsResult(
        trade_date=trade_date,
        requested_trade_date=requested_trade_date,
        anchor_count=anchor_count,
        member_count=member_count,
        source_counts=refreshed.source_counts,
        failed_sources=refreshed.failed_sources,
        refreshed=True,
    )


def resolve_market_anchor_trade_date(
    config: RadarConfig,
    *,
    trade_date: str,
    tushare_call: TushareCallFn | None = None,
    lookback_days: int = 45,
) -> str:
    """如果请求日期不是交易日，回退到它之前最近的交易日。"""

    _validate_trade_date(trade_date)
    if lookback_days < 1:
        raise ValueError("lookback_days 必须大于 0")

    requested = datetime.strptime(trade_date, "%Y%m%d").date()
    start_date = requested - timedelta(days=lookback_days)
    fetch = tushare_call or (
        lambda cfg, api_name, params, fields: call_tushare(
            cfg,
            api_name,
            params,
            fields=fields,
            use_cache=True,
        )
    )
    rows = fetch(
        config,
        "trade_cal",
        {
            "exchange": "",
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": trade_date,
        },
        "cal_date,is_open",
    )

    open_dates: list[str] = []
    requested_is_open = False
    for row in rows:
        cal_date = _text(row.get("cal_date"))
        if not re.fullmatch(r"\d{8}", cal_date) or cal_date > trade_date:
            continue
        is_open = str(row.get("is_open")) in {"1", "1.0", "True", "true"}
        if is_open:
            open_dates.append(cal_date)
        if cal_date == trade_date:
            requested_is_open = is_open

    if requested_is_open:
        return trade_date
    return max(open_dates) if open_dates else trade_date


def refresh_market_anchors(
    config: RadarConfig,
    *,
    trade_date: str,
    use_cache: bool = True,
    tushare_call: TushareCallFn | None = None,
) -> RefreshMarketAnchorsResult:
    """刷新某个交易日的市场 anchor 词库；原始 Tushare 响应仍走 KV 缓存。"""

    _validate_trade_date(trade_date)
    fetch = tushare_call or (
        lambda cfg, api_name, params, fields: call_tushare(
            cfg,
            api_name,
            params,
            fields=fields,
            use_cache=use_cache,
        )
    )
    anchors: dict[str, MarketAnchor] = {}
    members: dict[tuple[str, str, str, str], MarketAnchorMember] = {}
    source_counts: dict[str, int] = {}
    failed_sources: dict[str, str] = {}

    from radar.core.market_anchor_sources import LOADERS

    for loader in LOADERS:
        try:
            loaded_anchors, loaded_members, counts = loader(config, trade_date, fetch)
        except Exception as exc:  # noqa: BLE001 - 每个外部源独立降级，保留可用词库。
            failed_sources[loader.__name__.removeprefix("_load_")] = str(exc)
            continue
        for anchor in loaded_anchors:
            anchors[anchor.anchor_id] = _merge_anchor(anchors.get(anchor.anchor_id), anchor)
        for member in loaded_members:
            members[(member.anchor_id, member.ts_code, member.source, member.trade_date)] = member
        source_counts.update(counts)

    _replace_sources(
        config,
        trade_date,
        list(source_counts),
        list(anchors.values()),
        list(members.values()),
    )
    return RefreshMarketAnchorsResult(
        trade_date=trade_date,
        anchor_count=len(anchors),
        member_count=len(members),
        source_counts=source_counts,
        failed_sources=failed_sources,
    )


def list_market_anchors(config: RadarConfig, *, trade_date: str, limit: int = 50) -> list[MarketAnchor]:
    _validate_trade_date(trade_date)
    if limit < 1:
        raise ValueError("limit 必须大于 0")
    with _connect(config) as conn:
        rows = conn.execute(
            """
            SELECT anchor_id, anchor_type, name, aliases_json, source, source_code,
                   trade_date, hot_score, metadata_json
            FROM market_anchors
            WHERE trade_date = ?
            ORDER BY COALESCE(hot_score, 0) DESC, name
            LIMIT ?
            """,
            (trade_date, limit),
        ).fetchall()
    return [_row_to_anchor(row) for row in rows]


def refresh_market_anchor_derivatives(config: RadarConfig) -> RefreshMarketAnchorDerivativesResult:
    """从原始每日 anchor 快照重建 latest/current 和区间压缩派生表。"""

    with _connect(config) as conn:
        return _rebuild_market_anchor_derivatives(conn)


def _replace_sources(
    config: RadarConfig,
    trade_date: str,
    sources: list[str],
    anchors: list[MarketAnchor],
    members: list[MarketAnchorMember],
) -> None:
    if not sources:
        return
    now = datetime.now().isoformat(timespec="seconds")
    anchor_ids = {anchor.anchor_id for anchor in anchors}
    source_placeholders = ",".join("?" for _ in sources)
    with _connect(config) as conn:
        conn.execute(
            f"""
            DELETE FROM market_anchor_members
            WHERE trade_date = ?
              AND (source IN ({source_placeholders})
                   OR anchor_id IN (
                       SELECT anchor_id FROM market_anchors
                       WHERE trade_date = ? AND source IN ({source_placeholders})
                   ))
            """,
            [trade_date, *sources, trade_date, *sources],
        )
        conn.execute(
            f"DELETE FROM market_anchors WHERE trade_date = ? AND source IN ({source_placeholders})",
            [trade_date, *sources],
        )
        conn.executemany(
            """
            INSERT INTO market_anchors (
                anchor_id, anchor_type, name, aliases_json, source, source_code,
                trade_date, hot_score, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.anchor_id,
                    item.anchor_type,
                    item.name,
                    json.dumps(item.aliases, ensure_ascii=False),
                    item.source,
                    item.source_code,
                    item.trade_date,
                    item.hot_score,
                    json.dumps(item.metadata, ensure_ascii=False, default=str),
                    now,
                )
                for item in anchors
            ],
        )
        conn.executemany(
            """
            INSERT INTO market_anchor_members (
                anchor_id, ts_code, stock_name, reason, source, trade_date, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.anchor_id,
                    item.ts_code,
                    item.stock_name,
                    item.reason,
                    item.source,
                    item.trade_date,
                    json.dumps(item.metadata, ensure_ascii=False, default=str),
                )
                for item in members
                if item.anchor_id in anchor_ids
            ],
        )
        _rebuild_market_anchor_derivatives(conn)
        from radar.core.market_themes import rebuild_market_theme_normalization_from_conn

        rebuild_market_theme_normalization_from_conn(conn, commit=False)
        conn.commit()


def _rebuild_market_anchor_derivatives(conn: sqlite3.Connection) -> RefreshMarketAnchorDerivativesResult:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("DELETE FROM market_anchor_current_members")
    conn.execute("DELETE FROM market_anchor_member_spans")
    conn.execute(
        """
        INSERT INTO market_anchor_current_members (
            anchor_key, anchor_type, anchor_name, anchor_source, source_code,
            member_source, ts_code, stock_name, reason, latest_trade_date,
            hot_score, anchor_metadata_json, member_metadata_json, updated_at
        )
        WITH joined AS (
            SELECT
                a.source || ':' || a.source_code AS anchor_key,
                a.anchor_type,
                a.name AS anchor_name,
                a.source AS anchor_source,
                a.source_code,
                m.source AS member_source,
                m.ts_code,
                m.stock_name,
                m.reason,
                m.trade_date,
                a.hot_score,
                a.metadata_json AS anchor_metadata_json,
                m.metadata_json AS member_metadata_json,
                ROW_NUMBER() OVER (
                    PARTITION BY a.source, a.source_code, a.anchor_type, m.source, m.ts_code
                    ORDER BY m.trade_date DESC, m.stock_name
                ) AS row_rank
            FROM market_anchor_members m
            JOIN market_anchors a ON a.anchor_id = m.anchor_id
        )
        SELECT
            anchor_key, anchor_type, anchor_name, anchor_source, source_code,
            member_source, ts_code, stock_name, reason, trade_date,
            hot_score, anchor_metadata_json, member_metadata_json, ?
        FROM joined
        WHERE row_rank = 1
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO market_anchor_member_spans (
            anchor_key, anchor_type, anchor_name, anchor_source, source_code,
            member_source, ts_code, stock_name, first_seen_date, last_seen_date,
            seen_days, latest_reason, latest_hot_score, anchor_metadata_json,
            member_metadata_json, updated_at
        )
        WITH joined AS (
            SELECT
                a.source || ':' || a.source_code AS anchor_key,
                a.anchor_type,
                a.name AS anchor_name,
                a.source AS anchor_source,
                a.source_code,
                m.source AS member_source,
                m.ts_code,
                m.stock_name,
                m.reason,
                m.trade_date,
                a.hot_score,
                a.metadata_json AS anchor_metadata_json,
                m.metadata_json AS member_metadata_json,
                ROW_NUMBER() OVER (
                    PARTITION BY a.source, a.source_code, a.anchor_type, m.source, m.ts_code
                    ORDER BY m.trade_date DESC, m.stock_name
                ) AS row_rank
            FROM market_anchor_members m
            JOIN market_anchors a ON a.anchor_id = m.anchor_id
        ),
        grouped AS (
            SELECT
                anchor_key,
                member_source,
                ts_code,
                MIN(trade_date) AS first_seen_date,
                MAX(trade_date) AS last_seen_date,
                COUNT(DISTINCT trade_date) AS seen_days
            FROM joined
            GROUP BY anchor_key, member_source, ts_code
        )
        SELECT
            latest.anchor_key,
            latest.anchor_type,
            latest.anchor_name,
            latest.anchor_source,
            latest.source_code,
            latest.member_source,
            latest.ts_code,
            latest.stock_name,
            grouped.first_seen_date,
            grouped.last_seen_date,
            grouped.seen_days,
            latest.reason,
            latest.hot_score,
            latest.anchor_metadata_json,
            latest.member_metadata_json,
            ?
        FROM joined latest
        JOIN grouped
          ON grouped.anchor_key = latest.anchor_key
         AND grouped.member_source = latest.member_source
         AND grouped.ts_code = latest.ts_code
        WHERE latest.row_rank = 1
        """,
        (now,),
    )
    latest_row = conn.execute("SELECT MAX(latest_trade_date) FROM market_anchor_current_members").fetchone()
    current_count = conn.execute("SELECT COUNT(*) FROM market_anchor_current_members").fetchone()[0]
    span_count = conn.execute("SELECT COUNT(*) FROM market_anchor_member_spans").fetchone()[0]
    return RefreshMarketAnchorDerivativesResult(
        latest_trade_date=str(latest_row[0]) if latest_row and latest_row[0] else None,
        current_count=int(current_count),
        span_count=int(span_count),
    )


def _stored_counts(config: RadarConfig, trade_date: str) -> tuple[int, int]:
    with _connect(config) as conn:
        anchor_count = conn.execute(
            "SELECT COUNT(*) FROM market_anchors WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()[0]
        member_count = conn.execute(
            "SELECT COUNT(*) FROM market_anchor_members WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()[0]
    return int(anchor_count), int(member_count)


def _latest_stored_anchor_trade_date(
    config: RadarConfig,
    *,
    before_trade_date: str,
    min_anchor_count: int,
) -> str | None:
    with _connect(config) as conn:
        row = conn.execute(
            """
            SELECT trade_date
            FROM market_anchors
            WHERE trade_date < ?
            GROUP BY trade_date
            HAVING COUNT(*) >= ?
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (before_trade_date, min_anchor_count),
        ).fetchone()
    return str(row["trade_date"]) if row is not None else None


def _connect(config: RadarConfig) -> sqlite3.Connection:
    config.market_database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.market_database_path)
    conn.row_factory = sqlite3.Row
    migrate_market_db(conn)
    return conn


def _row_to_anchor(row: sqlite3.Row) -> MarketAnchor:
    return MarketAnchor(
        anchor_id=row["anchor_id"],
        anchor_type=row["anchor_type"],
        name=row["name"],
        aliases=json.loads(row["aliases_json"]),
        source=row["source"],
        source_code=row["source_code"],
        trade_date=row["trade_date"],
        hot_score=row["hot_score"],
        metadata=json.loads(row["metadata_json"]),
    )


def _merge_anchor(existing: MarketAnchor | None, incoming: MarketAnchor) -> MarketAnchor:
    if existing is None:
        return incoming
    aliases = sorted({*existing.aliases, *incoming.aliases})
    hot_score = max(existing.hot_score or 0, incoming.hot_score or 0) or None
    return existing.model_copy(
        update={
            "aliases": aliases,
            "hot_score": hot_score,
            "metadata": existing.metadata | incoming.metadata,
        }
    )


def _anchor_id(source: str, source_code: str, trade_date: str) -> str:
    clean_code = re.sub(r"\s+", "_", source_code.strip())
    return f"{source}:{trade_date}:{clean_code}"


def _split_themes(value: str) -> list[str]:
    parts = re.split(r"[、,，/]+", value)
    return [part.strip() for part in parts if part.strip()]


def _compact_metadata(row: dict[str, Any], excluded: set[str]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in excluded and value not in (None, "")}


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _validate_trade_date(trade_date: str) -> None:
    if not re.fullmatch(r"\d{8}", trade_date):
        raise ValueError("trade_date 必须是 YYYYMMDD")
