from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
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
    refreshed: bool = False
    skipped_reason: str | None = None


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
            anchor_count=existing_anchor_count,
            member_count=existing_member_count,
            refreshed=False,
            skipped_reason="anchor 词库已存在",
        )

    refreshed = refresh_market_anchors(
        config,
        trade_date=trade_date,
        use_cache=use_cache,
        tushare_call=tushare_call,
    )
    anchor_count, member_count = _stored_counts(config, trade_date)
    return EnsureMarketAnchorsResult(
        trade_date=trade_date,
        anchor_count=anchor_count,
        member_count=member_count,
        source_counts=refreshed.source_counts,
        failed_sources=refreshed.failed_sources,
        refreshed=True,
    )


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
        conn.commit()


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
