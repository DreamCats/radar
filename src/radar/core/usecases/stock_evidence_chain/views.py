from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.store import connect, init_db
from radar.core.usecases.stock_evidence_chain.llm import STAGE_LABELS

STAGE_ACTION_PRIORITY = {
    "seed": 60,
    "formed": 60,
    "lead": 50,
    "spreading": 45,
    "pricing": 25,
    "crowded": 5,
}
FAMILY_WEIGHTS = {
    "catalyst": 5,
    "roadshow": 4,
    "research": 3,
    "push": 3,
    "price": 1,
}


class StockEvidenceMarketPoint(BaseModel):
    trade_date: str
    close: float | None = None
    pct_chg: float | None = None
    amount: float | None = None
    amount_ratio_5d: float | None = None
    tag: str | None = None


class StockEvidenceMessage(BaseModel):
    message_id: str | None = None
    time: str | None = None
    type: str | None = None
    evidence: str | None = None
    sender: str | None = None
    group_name: str | None = None
    raw_content: str | None = None


class StockEvidenceChainItem(BaseModel):
    ts_code: str
    stock_name: str
    stage: str
    stage_label: str
    confidence: float | None = None
    rank: int | None = None
    summary: str
    trigger_count: int
    unique_trigger_count: int
    sender_count: int
    conversation_count: int
    evidence_count: int
    channels: list[str] = Field(default_factory=list)
    family_counts: dict[str, int] = Field(default_factory=dict)
    why: list[str] = Field(default_factory=list)
    incremental_valid: bool | None = None
    incremental_points: list[str] = Field(default_factory=list)
    pricing_risk: str | None = None
    crowding_risk: str | None = None
    watch_next: list[str] = Field(default_factory=list)
    evidence_chain: list[StockEvidenceMessage] = Field(default_factory=list)
    market_summary: dict[str, Any] = Field(default_factory=dict)
    market_points: list[StockEvidenceMarketPoint] = Field(default_factory=list)
    updated_at: datetime


class StockEvidenceChainDashboard(BaseModel):
    as_of_time: datetime | None = None
    window_start_time: datetime | None = None
    evidence_start_time: datetime | None = None
    generated_at: datetime
    item_count: int = 0
    stage_counts: dict[str, int] = Field(default_factory=dict)
    items: list[StockEvidenceChainItem] = Field(default_factory=list)


def latest_stock_evidence_chain(config: RadarConfig, *, limit: int = 120) -> StockEvidenceChainDashboard:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        as_of = _latest_as_of(conn)
        if as_of is None:
            return StockEvidenceChainDashboard(generated_at=datetime.now())
        rows = conn.execute(
            """
            SELECT
                j.*,
                c.rank AS candidate_rank,
                c.evidence_score AS candidate_evidence_score,
                c.family_counts_json AS candidate_family_counts_json
            FROM stock_lifecycle_judgements j
            LEFT JOIN stock_lifecycle_candidates c
              ON c.as_of_time = j.as_of_time
             AND c.ts_code = j.ts_code
            WHERE j.as_of_time = ?
            ORDER BY COALESCE(c.rank, 999999), j.updated_at DESC
            """,
            (as_of,),
        ).fetchall()
        rows = sorted(rows, key=_actionable_sort_key)[:limit]
        messages = _load_messages(conn, rows)
        items = [_row_to_item(row, messages) for row in rows]
        return StockEvidenceChainDashboard(
            as_of_time=datetime.fromisoformat(as_of),
            window_start_time=_datetime(rows[0]["window_start_time"]) if rows else None,
            evidence_start_time=_datetime(rows[0]["evidence_start_time"]) if rows else None,
            generated_at=datetime.now(),
            item_count=len(items),
            stage_counts=_stage_counts(items),
            items=items,
        )
    finally:
        conn.close()


def _latest_as_of(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(as_of_time) FROM stock_lifecycle_judgements").fetchone()
    value = row[0] if row else None
    return str(value) if value else None


def _load_messages(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> dict[str, sqlite3.Row]:
    ids: set[str] = set()
    for row in rows:
        for ref in _json_list(row["evidence_refs_json"]):
            message_id = str(ref.get("message_id") or "")
            if message_id:
                ids.add(message_id)
        for point in _json_list(_result(row).get("evidence_chain")):
            message_id = str(point.get("message_id") or "")
            if message_id:
                ids.add(message_id)
    if not ids:
        return {}
    result: dict[str, sqlite3.Row] = {}
    ordered = sorted(ids)
    for start in range(0, len(ordered), 500):
        chunk = ordered[start : start + 500]
        placeholders = ", ".join("?" for _ in chunk)
        for msg in conn.execute(
            f"SELECT message_id, sender, group_name, raw_content FROM messages WHERE message_id IN ({placeholders})",
            chunk,
        ).fetchall():
            result[str(msg["message_id"])] = msg
    return result


def _row_to_item(row: sqlite3.Row, messages: dict[str, sqlite3.Row]) -> StockEvidenceChainItem:
    result = _result(row)
    stage = str(row["stage"])
    incremental = result.get("incremental") if isinstance(result.get("incremental"), dict) else {}
    market = result.get("market_evidence") if isinstance(result.get("market_evidence"), dict) else {}
    return StockEvidenceChainItem(
        ts_code=str(row["ts_code"]),
        stock_name=str(row["stock_name"]),
        stage=stage,
        stage_label=str(result.get("stage_label") or STAGE_LABELS.get(stage, stage)),
        confidence=_float(row["confidence"]),
        rank=_int(row["candidate_rank"]),
        summary=str(result.get("one_line") or result.get("summary") or ""),
        trigger_count=int(row["trigger_count"] or 0),
        unique_trigger_count=int(row["unique_trigger_count"] or 0),
        sender_count=int(row["sender_count"] or 0),
        conversation_count=int(row["conversation_count"] or 0),
        evidence_count=int(row["evidence_count"] or 0),
        channels=[str(item) for item in _json_list(row["channels_json"])],
        family_counts=_json_dict(row["candidate_family_counts_json"]),
        why=[str(item) for item in _json_list(result.get("why"))],
        incremental_valid=incremental.get("valid") if isinstance(incremental.get("valid"), bool) else None,
        incremental_points=[str(item) for item in _json_list(incremental.get("points"))],
        pricing_risk=_optional_text(result.get("pricing_risk")),
        crowding_risk=_optional_text(result.get("crowding_risk")),
        watch_next=[str(item) for item in _json_list(result.get("watch_next"))],
        evidence_chain=_evidence_chain(result, row, messages),
        market_summary=market.get("summary") if isinstance(market.get("summary"), dict) else {},
        market_points=[StockEvidenceMarketPoint(**point) for point in _json_list(market.get("points")) if isinstance(point, dict)],
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _evidence_chain(result: dict[str, Any], row: sqlite3.Row, messages: dict[str, sqlite3.Row]) -> list[StockEvidenceMessage]:
    refs = {str(ref.get("message_id") or ""): ref for ref in _json_list(row["evidence_refs_json"]) if isinstance(ref, dict)}
    points = _json_list(result.get("evidence_chain"))
    items: list[StockEvidenceMessage] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        message_id = str(point.get("message_id") or "")
        ref = refs.get(message_id, {})
        message = messages.get(message_id)
        items.append(
            StockEvidenceMessage(
                message_id=message_id or None,
                time=_optional_text(point.get("time")) or _optional_text(ref.get("message_time")),
                type=_optional_text(point.get("type")),
                evidence=_optional_text(point.get("evidence")),
                sender=_optional_text(ref.get("sender")) or _row_text(message, "sender"),
                group_name=_optional_text(ref.get("group_name")) or _row_text(message, "group_name"),
                raw_content=_row_text(message, "raw_content"),
            )
        )
    return items


def _result(row: sqlite3.Row) -> dict[str, Any]:
    return _json_dict(row["result_json"])


def _stage_counts(items: list[StockEvidenceChainItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = item.stage_label or item.stage
        counts[key] = counts.get(key, 0) + 1
    return counts


def _actionable_sort_key(row: sqlite3.Row) -> tuple[int, int, int, int, int, int, str]:
    result = _result(row)
    stage = str(row["stage"])
    family_counts = _json_dict(row["candidate_family_counts_json"])
    market = result.get("market_evidence") if isinstance(result.get("market_evidence"), dict) else {}
    summary = market.get("summary") if isinstance(market.get("summary"), dict) else {}
    return_rate = _float(summary.get("return_since_first_point"))
    drawdown = _float(summary.get("drawdown_from_selected_high"))
    confidence = _float(row["confidence"]) or 0
    rank = _int(row["candidate_rank"]) or 999999
    updated_at = str(row["updated_at"])
    return (
        -STAGE_ACTION_PRIORITY.get(stage, 30),
        -_stage_specific_score(row, stage=stage, family_counts=family_counts, return_rate=return_rate, drawdown=drawdown),
        -_incremental_score(result),
        -_diffusion_score(row),
        -int(confidence * 100),
        rank,
        _reverse_time_key(updated_at),
    )


def _stage_specific_score(
    row: sqlite3.Row,
    *,
    stage: str,
    family_counts: dict[str, Any],
    return_rate: float | None,
    drawdown: float | None,
) -> int:
    evidence = _evidence_strength(row, family_counts)
    if stage == "crowded":
        return _priced_risk_score(return_rate, drawdown) + _diffusion_score(row)
    if stage == "pricing":
        return evidence + _market_confirmation_score(return_rate, drawdown)
    return evidence + _underpriced_score(return_rate)


def _evidence_strength(row: sqlite3.Row, family_counts: dict[str, Any]) -> int:
    score = _int(row["candidate_evidence_score"]) or 0
    for family, weight in FAMILY_WEIGHTS.items():
        score += (_int(family_counts.get(family)) or 0) * weight
    return score


def _incremental_score(result: dict[str, Any]) -> int:
    incremental = result.get("incremental") if isinstance(result.get("incremental"), dict) else {}
    points = _json_list(incremental.get("points"))
    return (8 if incremental.get("valid") is True else 0) + min(len(points), 4)


def _diffusion_score(row: sqlite3.Row) -> int:
    unique = int(row["unique_trigger_count"] or 0)
    senders = int(row["sender_count"] or 0)
    conversations = int(row["conversation_count"] or 0)
    return min(unique, 12) + min(senders, 6) * 2 + min(conversations, 6) * 2


def _underpriced_score(return_rate: float | None) -> int:
    if return_rate is None:
        return 4
    if return_rate < 0.05:
        return 16
    if return_rate < 0.15:
        return 12
    if return_rate < 0.30:
        return 5
    if return_rate < 0.50:
        return -4
    return -12


def _market_confirmation_score(return_rate: float | None, drawdown: float | None) -> int:
    score = 0
    if return_rate is not None:
        score += min(max(int(return_rate * 100), 0), 40)
    if drawdown is not None and drawdown > -0.12:
        score += 6
    return score


def _priced_risk_score(return_rate: float | None, drawdown: float | None) -> int:
    score = 0
    if return_rate is not None:
        score += min(max(int(return_rate * 100), 0), 80)
    if drawdown is not None and drawdown < -0.12:
        score += 8
    return score


def _reverse_time_key(value: str) -> str:
    return "".join(chr(255 - ord(char)) for char in value)


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _datetime(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _row_text(row: sqlite3.Row | None, key: str) -> str | None:
    if row is None:
        return None
    value = row[key]
    return str(value) if value else None
