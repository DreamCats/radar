from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from radar.core.models import MessageSource
from radar.core.organize import OrganizeEvidenceMessage
from radar.core.usecases.aggregation.models import RefinedTheme, RefineAggregateTopicsResult


class OrganizeAggregateFilters(BaseModel):
    """历史聚合结果读取：只读取已落库的 refine 结果，不触发离线任务。"""

    source: MessageSource | None = None
    keyword: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    evidence_limit: int = Field(default=30, ge=0, le=100)


class OrganizeAggregateEvidenceFilters(BaseModel):
    run_id: str
    theme_index: int = Field(ge=0)
    source: MessageSource | None = None
    keyword: str | None = None
    cursor_time: datetime | None = None
    cursor_id: str | None = None
    limit: int = Field(default=30, ge=1, le=50)


class OrganizeAggregateSummary(BaseModel):
    run_id: str
    input_hash: str
    status: str
    trade_date: str
    start_time: datetime
    end_time: datetime
    candidate_count: int
    theme_count: int
    llm_batch_count: int
    failed_llm_batches: int
    max_concurrency: int
    evidence_message_count: int


class OrganizeAggregateTheme(BaseModel):
    theme_index: int
    theme_name: str
    aliases: list[str]
    summary: str
    investment_logic: str
    catalysts: list[str]
    related_stocks: list[dict[str, object]]
    evidence_message_ids: list[str]
    novelty: str
    confidence: float
    actionability_score: float
    priority_score: float
    risk_notes: list[str]
    merge_from_candidate_ids: list[str]
    evidence: list[OrganizeEvidenceMessage]


class OrganizeAggregatePage(BaseModel):
    result: OrganizeAggregateSummary | None = None
    themes: list[OrganizeAggregateTheme] = Field(default_factory=list)


class OrganizeAggregateEvidencePage(BaseModel):
    items: list[OrganizeEvidenceMessage]
    next_cursor_time: datetime | None = None
    next_cursor_id: str | None = None


def list_aggregate_themes(conn: sqlite3.Connection, filters: OrganizeAggregateFilters) -> OrganizeAggregatePage:
    result = _latest_refine_result(conn, filters)
    if result is None:
        return OrganizeAggregatePage()

    keyword = filters.keyword.strip().lower() if filters.keyword else ""
    themes = [
        _theme_to_organize_theme(conn, result, index, theme, filters)
        for index, theme in enumerate(result.themes)
        if not keyword or _theme_matches_keyword(theme, keyword)
    ]
    themes.sort(key=lambda item: (-item.priority_score, -item.actionability_score, -item.confidence, item.theme_name))
    message_ids = {message_id for theme in themes for message_id in theme.evidence_message_ids}
    summary = OrganizeAggregateSummary(
        run_id=result.run_id,
        input_hash=result.input_hash,
        status=result.status,
        trade_date=result.trade_date,
        start_time=result.local_result.start_time,
        end_time=result.local_result.end_time,
        candidate_count=result.candidate_count,
        theme_count=len(themes),
        llm_batch_count=result.llm_batch_count,
        failed_llm_batches=result.failed_llm_batches,
        max_concurrency=result.max_concurrency,
        evidence_message_count=len(message_ids),
    )
    return OrganizeAggregatePage(result=summary, themes=themes)


def list_aggregate_evidence(
    conn: sqlite3.Connection,
    filters: OrganizeAggregateEvidenceFilters,
) -> OrganizeAggregateEvidencePage:
    result = _refine_result_by_run_id(conn, filters.run_id)
    if result is None or filters.theme_index >= len(result.themes):
        return OrganizeAggregateEvidencePage(items=[])

    theme = result.themes[filters.theme_index]
    items = _evidence_for_ids(
        conn,
        _unique_ids(theme.evidence_message_ids),
        source=filters.source,
        keyword=filters.keyword,
        limit=filters.limit + 1,
        cursor_time=filters.cursor_time,
        cursor_id=filters.cursor_id,
    )
    page_items = items[: filters.limit]
    if len(items) <= filters.limit or not page_items:
        return OrganizeAggregateEvidencePage(items=page_items)
    last = page_items[-1]
    return OrganizeAggregateEvidencePage(items=page_items, next_cursor_time=last.message_time, next_cursor_id=last.message_id)


def _latest_refine_result(
    conn: sqlite3.Connection,
    filters: OrganizeAggregateFilters,
) -> RefineAggregateTopicsResult | None:
    where: list[str] = []
    params: list[object] = []
    if filters.start_time:
        where.append("a.end_time >= ?")
        params.append(filters.start_time.isoformat())
    if filters.end_time:
        where.append("a.start_time <= ?")
        params.append(filters.end_time.isoformat())

    sql = [
        """
        SELECT a.result_json, r.metadata_json
        FROM aggregate_refine_results a
        LEFT JOIN runs r ON r.run_id = a.run_id
        """
    ]
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY a.updated_at DESC LIMIT 20")

    for row in conn.execute(" ".join(sql), params).fetchall():
        if _source_matches(row["metadata_json"], filters.source):
            return RefineAggregateTopicsResult.model_validate_json(row["result_json"])
    return None


def _refine_result_by_run_id(conn: sqlite3.Connection, run_id: str) -> RefineAggregateTopicsResult | None:
    row = conn.execute(
        """
        SELECT result_json
        FROM aggregate_refine_results
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return RefineAggregateTopicsResult.model_validate_json(row["result_json"])


def _source_matches(metadata_json: str | None, source: MessageSource | None) -> bool:
    if source is None:
        return True
    metadata = _metadata(metadata_json)
    stored_source = metadata.get("source")
    if stored_source is None:
        return True
    expected = "personal_message" if source == "个人消息" else "group_message"
    return stored_source in {"all", expected}


def _theme_to_organize_theme(
    conn: sqlite3.Connection,
    result: RefineAggregateTopicsResult,
    index: int,
    theme: RefinedTheme,
    filters: OrganizeAggregateFilters,
) -> OrganizeAggregateTheme:
    evidence_ids = _unique_ids(theme.evidence_message_ids)
    stats = _evidence_stats_for_ids(conn, evidence_ids, source=filters.source)
    priority_score = _priority_score(
        theme,
        evidence_count=stats["count"],
        latest_message_time=stats["latest_message_time"],
        start_time=filters.start_time or result.local_result.start_time,
        end_time=filters.end_time or result.local_result.end_time,
    )
    return OrganizeAggregateTheme(
        theme_index=index,
        theme_name=theme.theme_name,
        aliases=theme.aliases,
        summary=theme.summary,
        investment_logic=theme.investment_logic,
        catalysts=theme.catalysts,
        related_stocks=[stock.model_dump() for stock in theme.related_stocks],
        evidence_message_ids=evidence_ids,
        novelty=theme.novelty,
        confidence=theme.confidence,
        actionability_score=theme.actionability_score,
        priority_score=priority_score,
        risk_notes=theme.risk_notes,
        merge_from_candidate_ids=theme.merge_from_candidate_ids,
        evidence=_evidence_for_ids(
            conn,
            evidence_ids,
            source=filters.source,
            keyword=filters.keyword,
            limit=filters.evidence_limit,
        ),
    )


def _evidence_stats_for_ids(
    conn: sqlite3.Connection,
    message_ids: list[str],
    *,
    source: MessageSource | None,
) -> dict[str, Any]:
    if not message_ids:
        return {"count": 0, "latest_message_time": None}
    placeholders = ", ".join("?" for _ in message_ids)
    where = [f"message_id IN ({placeholders})"]
    params: list[object] = list(message_ids)
    if source:
        where.append("source = ?")
        params.append(source)

    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count, MAX(message_time) AS latest_message_time
        FROM messages
        WHERE {" AND ".join(where)}
        """,
        params,
    ).fetchone()
    latest = datetime.fromisoformat(row["latest_message_time"]) if row and row["latest_message_time"] else None
    return {"count": row["count"] if row else 0, "latest_message_time": latest}


def _priority_score(
    theme: RefinedTheme,
    *,
    evidence_count: int,
    latest_message_time: datetime | None,
    start_time: datetime,
    end_time: datetime,
) -> float:
    actionability = _clamp(theme.actionability_score, 0, 100)
    confidence = _clamp(theme.confidence * 100, 0, 100)
    evidence = min(evidence_count, 10) / 10 * 100
    novelty = _novelty_score(theme.novelty)
    recency = _recency_score(latest_message_time, start_time=start_time, end_time=end_time)
    return round(actionability * 0.40 + confidence * 0.20 + evidence * 0.15 + novelty * 0.15 + recency * 0.10, 2)


def _novelty_score(novelty: str) -> float:
    return {
        "new": 100,
        "continuing": 75,
        "medium": 65,
        "unknown": 50,
        "repeated_noise": 20,
    }.get(novelty, 50)


def _recency_score(latest_message_time: datetime | None, *, start_time: datetime, end_time: datetime) -> float:
    if latest_message_time is None:
        return 0
    duration = (end_time - start_time).total_seconds()
    if duration <= 0:
        return 100
    elapsed = (latest_message_time - start_time).total_seconds()
    return _clamp(elapsed / duration * 100, 0, 100)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _evidence_for_ids(
    conn: sqlite3.Connection,
    message_ids: list[str],
    *,
    source: MessageSource | None,
    keyword: str | None,
    limit: int,
    cursor_time: datetime | None = None,
    cursor_id: str | None = None,
) -> list[OrganizeEvidenceMessage]:
    if not message_ids or limit <= 0:
        return []
    placeholders = ", ".join("?" for _ in message_ids)
    where = [f"m.message_id IN ({placeholders})"]
    params: list[object] = list(message_ids)
    if source:
        where.append("m.source = ?")
        params.append(source)
    if keyword:
        like = f"%{keyword.strip()}%"
        where.append("(m.raw_content LIKE ? OR m.sender LIKE ? OR COALESCE(m.group_name, '') LIKE ? OR COALESCE(c.reason, '') LIKE ?)")
        params.extend([like, like, like, like])
    if cursor_time and cursor_id:
        where.append("(m.message_time, m.message_id) < (?, ?)")
        params.extend([cursor_time.isoformat(), cursor_id])

    sql = f"""
        SELECT
            m.message_id, m.source, m.sender, m.group_name, m.message_time, m.raw_content,
            COALESCE(c.category, 'unknown') AS category,
            COALESCE(c.confidence, 0) AS confidence,
            COALESCE(c.reason, '') AS reason,
            COALESCE(c.status, 'needs_review') AS status
        FROM messages m
        LEFT JOIN message_classifications c ON c.message_id = m.message_id
        WHERE {" AND ".join(where)}
        ORDER BY m.message_time DESC, m.message_id DESC
        LIMIT ?
    """
    params.append(limit)
    return [_row_to_evidence(row) for row in conn.execute(sql, params).fetchall()]


def _row_to_evidence(row: sqlite3.Row) -> OrganizeEvidenceMessage:
    return OrganizeEvidenceMessage(
        message_id=row["message_id"],
        source=row["source"],
        sender=row["sender"],
        group_name=row["group_name"],
        message_time=datetime.fromisoformat(row["message_time"]),
        raw_content=row["raw_content"],
        category="research" if row["category"] == "tool_ad" else row["category"],
        confidence=row["confidence"],
        reason=row["reason"],
        status=row["status"],
    )


def _theme_matches_keyword(theme: RefinedTheme, keyword: str) -> bool:
    fields = [
        theme.theme_name,
        theme.summary,
        theme.investment_logic,
        theme.novelty,
        *theme.aliases,
        *theme.catalysts,
        *theme.risk_notes,
        *(stock.name for stock in theme.related_stocks),
        *(stock.reason for stock in theme.related_stocks),
    ]
    return any(keyword in field.lower() for field in fields if field)


def _unique_ids(message_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(message_ids))


def _metadata(metadata_json: str | None) -> dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        data = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
