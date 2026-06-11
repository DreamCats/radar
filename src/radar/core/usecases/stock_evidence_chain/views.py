from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from radar.core.config import RadarConfig
from radar.core.store import connect, init_db
from radar.core.usecases.stock_evidence_chain.lifecycle_models import (
    LIFECYCLE_DIGEST_SCOPE_TYPE,
    StockEvidenceLifecycleDigestContext,
)
from radar.core.usecases.stock_evidence_chain.llm import STAGE_LABELS
from radar.core.usecases.stock_evidence_chain.recognition import (
    StockEvidenceThemeContext,
    build_recognition_context,
    load_stock_theme_contexts,
    primary_theme,
)
from radar.core.usecases.stock_evidence_chain.review import (
    build_review_context,
    is_llm_output_invalid,
)
from radar.core.usecases.stock_evidence_chain.sorting import stock_evidence_item_sort_key
from radar.core.usecases.stock_evidence_chain.view_models import (
    StockEvidenceChainDashboard,
    StockEvidenceChainItem,
    StockEvidenceMarketPoint,
    StockEvidenceMessage,
)


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
        messages = _load_messages(conn, rows)
        theme_contexts = load_stock_theme_contexts(
            config,
            [str(row["ts_code"]) for row in rows],
            as_of=datetime.fromisoformat(as_of),
        )
        lifecycle_digests = _load_lifecycle_digests(conn, rows, theme_contexts)
        items = [
            _row_to_item(
                row,
                messages,
                theme_contexts.get(str(row["ts_code"]), []),
                lifecycle_digests.get(str(row["ts_code"])),
            )
            for row in rows
        ]
        items = sorted(items, key=stock_evidence_item_sort_key)[:limit]
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


def _row_to_item(
    row: sqlite3.Row,
    messages: dict[str, sqlite3.Row],
    themes: list[StockEvidenceThemeContext],
    lifecycle_digest: StockEvidenceLifecycleDigestContext | None,
) -> StockEvidenceChainItem:
    result = _result(row)
    stage = str(row["stage"])
    incremental = result.get("incremental") if isinstance(result.get("incremental"), dict) else {}
    market = result.get("market_evidence") if isinstance(result.get("market_evidence"), dict) else {}
    market_summary = market.get("summary") if isinstance(market.get("summary"), dict) else {}
    market_points = [StockEvidenceMarketPoint(**point) for point in _json_list(market.get("points")) if isinstance(point, dict)]
    raw_market_points = [point.model_dump() for point in market_points]
    primary = primary_theme(themes)
    confidence = _float(row["confidence"])
    raw_summary = str(result.get("one_line") or result.get("summary") or "")
    summary = _display_summary(raw_summary, confidence=confidence)
    recognition = build_recognition_context(
        unique_trigger_count=int(row["unique_trigger_count"] or 0),
        market_summary=market_summary,
        market_points=raw_market_points,
        themes=themes,
    )
    review = build_review_context(
        stage=stage,
        stage_label=str(result.get("stage_label") or STAGE_LABELS.get(stage, stage)),
        confidence=confidence,
        summary=raw_summary,
        unique_trigger_count=int(row["unique_trigger_count"] or 0),
        market_summary=market_summary,
        market_points=raw_market_points,
        primary_theme=primary,
        recognition=recognition,
    )
    return StockEvidenceChainItem(
        ts_code=str(row["ts_code"]),
        stock_name=str(row["stock_name"]),
        stage=stage,
        stage_label=str(result.get("stage_label") or STAGE_LABELS.get(stage, stage)),
        confidence=confidence,
        rank=_int(row["candidate_rank"]),
        summary=summary,
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
        market_summary=market_summary,
        market_points=market_points,
        themes=themes,
        primary_theme=primary,
        recognition=recognition,
        review=review,
        lifecycle_digest=lifecycle_digest,
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _load_lifecycle_digests(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    theme_contexts: dict[str, list[StockEvidenceThemeContext]],
) -> dict[str, StockEvidenceLifecycleDigestContext]:
    if not rows:
        return {}
    as_of = str(rows[0]["as_of_time"])
    scope_by_code: dict[str, str] = {}
    for row in rows:
        ts_code = str(row["ts_code"])
        theme = primary_theme(theme_contexts.get(ts_code, []))
        scope_by_code[ts_code] = f"{theme.theme_id}:{ts_code}" if theme is not None else f"stock:{ts_code}"
    if not scope_by_code:
        return {}
    scopes = sorted(scope_by_code.values())
    placeholders = ", ".join("?" for _ in scopes)
    digest_rows = conn.execute(
        f"""
        SELECT *
        FROM opportunity_lifecycle_digests
        WHERE as_of_time = ?
          AND scope_type = ?
          AND scope_key IN ({placeholders})
        ORDER BY updated_at DESC
        """,
        [as_of, LIFECYCLE_DIGEST_SCOPE_TYPE, *scopes],
    ).fetchall()
    by_scope: dict[str, sqlite3.Row] = {}
    for row in digest_rows:
        by_scope.setdefault(str(row["scope_key"]), row)
    result: dict[str, StockEvidenceLifecycleDigestContext] = {}
    for ts_code, scope_key in scope_by_code.items():
        row = by_scope.get(scope_key)
        if row is not None:
            result[ts_code] = _digest_context(row)
    return result


def _digest_context(row: sqlite3.Row) -> StockEvidenceLifecycleDigestContext:
    payload = _json_dict(row["digest_json"])
    return StockEvidenceLifecycleDigestContext(
        scope_key=str(row["scope_key"]),
        theme_id=_optional_text(row["theme_id"]),
        theme_name=_optional_text(row["theme_name"]),
        stage_label=STAGE_LABELS.get(str(row["stage"]), str(row["stage"])),
        recognition_label=_optional_text(row["recognition_state"]),
        one_line=str(payload.get("one_line") or ""),
        timeline=[str(item) for item in _json_list(payload.get("timeline"))],
        stage_reason=[str(item) for item in _json_list(payload.get("stage_reason"))],
        missing_evidence=[str(item) for item in _json_list(payload.get("missing_evidence"))],
        risk=[str(item) for item in _json_list(payload.get("risk"))],
        next_watch=[str(item) for item in _json_list(payload.get("next_watch"))],
        evidence_signature=str(row["evidence_signature"]),
        message_hash=_optional_text(row["message_hash"]),
        market_hash=_optional_text(row["market_hash"]),
        theme_hash=_optional_text(row["theme_hash"]),
        recognition_hash=_optional_text(row["recognition_hash"]),
        backtest_hash=_optional_text(row["backtest_hash"]),
        lifecycle_package_hash=_optional_text(row["lifecycle_package_hash"]),
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


def _display_summary(summary: str, *, confidence: float | None) -> str:
    if is_llm_output_invalid(summary=summary, confidence=confidence):
        return "LLM 生成异常，需重跑证据链后再判断。"
    return summary


def _result(row: sqlite3.Row) -> dict[str, Any]:
    return _json_dict(row["result_json"])


def _stage_counts(items: list[StockEvidenceChainItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = item.stage_label or item.stage
        counts[key] = counts.get(key, 0) + 1
    return counts


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
