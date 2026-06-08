from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from radar.core.algorithms.text_segments import segment_for_position, split_text_segments
from radar.core.config import RadarConfig
from radar.core.models import MessageCategory, MessageSource
from radar.core.store import connect, init_db
from radar.core.usecases.categories import normalize_derived_input_categories
from radar.core.usecases.aggregation.models import (
    AggregateTopic,
    AggregateTopicEvidence,
    AggregateTopicsResult,
    RelatedStock,
)
from radar.core.usecases.aggregation.scoring import TopicScoreCandidate, topic_score
from radar.core.usecases.anchoring import ANCHOR_EXTRACTOR_VERSION

_RowData = dict[str, Any]
_AGGREGATION_SEGMENT_CHARS = 180


def aggregate_topics(
    config: RadarConfig,
    *,
    trade_date: str,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None = None,
    categories: list[MessageCategory] | None = None,
    min_classification_confidence: float = 0.7,
    extractor_version: str = ANCHOR_EXTRACTOR_VERSION,
    min_messages: int = 2,
    limit: int = 20,
    evidence_limit: int = 3,
) -> AggregateTopicsResult:
    """基于 topic anchors 聚合主题；stock anchors 只作为相关标的证据。"""

    _validate_inputs(
        start_time,
        end_time,
        min_classification_confidence,
        min_messages,
        limit,
        evidence_limit,
    )
    category_values = normalize_derived_input_categories(categories)
    if not category_values:
        return AggregateTopicsResult(
            trade_date=trade_date,
            extractor_version=extractor_version,
            start_time=start_time,
            end_time=end_time,
            categories=category_values,
            min_classification_confidence=min_classification_confidence,
            scoped_message_count=0,
            anchored_message_count=0,
            topic_count=0,
            topics=[],
        )
    conn = connect(config.database_path)
    try:
        init_db(conn)
        topic_rows = _topic_rows(
            conn,
            trade_date=trade_date,
            start_time=start_time,
            end_time=end_time,
            source=source,
            categories=category_values,
            min_classification_confidence=min_classification_confidence,
            extractor_version=extractor_version,
        )
        stock_rows = _stock_rows(
            conn,
            trade_date=trade_date,
            start_time=start_time,
            end_time=end_time,
            source=source,
            categories=category_values,
            min_classification_confidence=min_classification_confidence,
            extractor_version=extractor_version,
        )
    finally:
        conn.close()

    enriched_topic_rows = _attach_segments(topic_rows)
    enriched_stock_rows = _attach_segments(stock_rows)
    noisy_segments = _noisy_relation_segments(enriched_topic_rows, enriched_stock_rows)
    stocks_by_segment = _stocks_by_segment(enriched_stock_rows, noisy_segments)
    topics = _build_topics(enriched_topic_rows, stocks_by_segment, min_messages, evidence_limit)
    topics.sort(key=lambda item: (-item.score, -item.message_count, item.name))
    scoped_message_ids = {str(row["message_id"]) for row in enriched_topic_rows} | {
        str(row["message_id"]) for row in enriched_stock_rows
    }
    anchored_message_ids = {str(row["message_id"]) for row in enriched_topic_rows}
    return AggregateTopicsResult(
        trade_date=trade_date,
        extractor_version=extractor_version,
        start_time=start_time,
        end_time=end_time,
        categories=category_values,
        min_classification_confidence=min_classification_confidence,
        scoped_message_count=len(scoped_message_ids),
        anchored_message_count=len(anchored_message_ids),
        topic_count=len(topics),
        topics=topics[:limit],
    )


def _topic_rows(
    conn: sqlite3.Connection,
    *,
    trade_date: str,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None,
    categories: list[MessageCategory],
    min_classification_confidence: float,
    extractor_version: str,
) -> list[sqlite3.Row]:
    where, params = _scope_conditions(
        trade_date,
        start_time,
        end_time,
        source,
        categories,
        min_classification_confidence,
        extractor_version,
    )
    where.append("a.anchor_type != 'stock'")
    sql = f"""
        SELECT
            a.message_id, a.anchor_type, a.name, a.confidence AS anchor_confidence,
            a.evidence_json,
            m.message_time, m.raw_content, m.sender, m.group_name,
            c.category, c.confidence AS classification_confidence
        FROM message_anchors a
        JOIN messages m ON m.message_id = a.message_id
        JOIN message_classifications c ON c.message_id = a.message_id
        WHERE {" AND ".join(where)}
        ORDER BY m.message_time DESC, a.confidence DESC
    """
    return conn.execute(sql, params).fetchall()


def _stock_rows(
    conn: sqlite3.Connection,
    *,
    trade_date: str,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None,
    categories: list[MessageCategory],
    min_classification_confidence: float,
    extractor_version: str,
) -> list[sqlite3.Row]:
    where, params = _scope_conditions(
        trade_date,
        start_time,
        end_time,
        source,
        categories,
        min_classification_confidence,
        extractor_version,
    )
    where.append("a.anchor_type = 'stock'")
    sql = f"""
        SELECT a.message_id, a.name, a.confidence, a.evidence_json, m.raw_content
        FROM message_anchors a
        JOIN messages m ON m.message_id = a.message_id
        JOIN message_classifications c ON c.message_id = a.message_id
        WHERE {" AND ".join(where)}
        ORDER BY a.confidence DESC, a.name
    """
    return conn.execute(sql, params).fetchall()


def _scope_conditions(
    trade_date: str,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None,
    categories: list[MessageCategory],
    min_classification_confidence: float,
    extractor_version: str,
) -> tuple[list[str], list[Any]]:
    placeholders = ", ".join("?" for _ in categories)
    where = [
        "a.trade_date = ?",
        "a.extractor_version = ?",
        "m.message_time >= ?",
        "m.message_time < ?",
        f"c.category IN ({placeholders})",
        "c.status != 'ignored'",
        "c.confidence >= ?",
    ]
    params: list[Any] = [
        trade_date,
        extractor_version,
        start_time.isoformat(),
        end_time.isoformat(),
        *categories,
        min_classification_confidence,
    ]
    if source:
        where.append("m.source = ?")
        params.append(source)
    return where, params


def _build_topics(
    rows: list[_RowData],
    stocks_by_segment: dict[tuple[str, int], list[str]],
    min_messages: int,
    evidence_limit: int,
) -> list[AggregateTopic]:
    grouped: dict[str, list[_RowData]] = defaultdict(list)
    for row in rows:
        grouped[_topic_key(str(row["name"]))].append(row)

    candidates: list[TopicScoreCandidate] = []
    stocks_by_topic_key: dict[str, list[RelatedStock]] = {}
    for topic_key, topic_rows in grouped.items():
        message_ids = frozenset(str(row["message_id"]) for row in topic_rows)
        if len(message_ids) < min_messages:
            continue
        stocks = _related_stocks(topic_rows, stocks_by_segment)
        stocks_by_topic_key[topic_key] = stocks
        candidates.append(
            TopicScoreCandidate(
                name=_display_name(topic_rows),
                rows=tuple(topic_rows),
                message_ids=message_ids,
                anchor_types=frozenset(row["anchor_type"] for row in topic_rows),
                related_stock_count=len(stocks),
            )
        )

    topics: list[AggregateTopic] = []
    for candidate in candidates:
        topic_rows = list(candidate.rows)
        stocks = stocks_by_topic_key[_topic_key(candidate.name)]
        evidence = _evidence(topic_rows, stocks_by_segment, evidence_limit)
        topics.append(
            AggregateTopic(
                name=candidate.name,
                anchor_types=sorted({row["anchor_type"] for row in topic_rows}, key=_anchor_type_order),
                message_count=len(candidate.message_ids),
                anchor_count=len(topic_rows),
                score=topic_score(candidate, candidates),
                latest_time=max(datetime.fromisoformat(row["message_time"]) for row in topic_rows),
                category_distribution=dict(Counter(row["category"] for row in topic_rows)),
                related_stocks=stocks,
                evidence=evidence,
            )
        )
    return topics


def _display_name(rows: list[_RowData]) -> str:
    return Counter(str(row["name"]) for row in rows).most_common(1)[0][0]


def _related_stocks(
    rows: list[_RowData],
    stocks_by_segment: dict[tuple[str, int], list[str]],
) -> list[RelatedStock]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(stocks_by_segment.get(_segment_key(row), []))
    return [RelatedStock(name=name, count=count) for name, count in counts.most_common(8)]


def _evidence(
    rows: list[_RowData],
    stocks_by_segment: dict[tuple[str, int], list[str]],
    evidence_limit: int,
) -> list[AggregateTopicEvidence]:
    best_by_message: dict[str, _RowData] = {}
    for row in rows:
        message_id = str(row["message_id"])
        existing = best_by_message.get(message_id)
        if existing is None or row["anchor_confidence"] > existing["anchor_confidence"]:
            best_by_message[message_id] = row
    sorted_rows = sorted(
        best_by_message.values(),
        key=lambda row: (row["message_time"], row["anchor_confidence"]),
        reverse=True,
    )
    return [_row_to_evidence(row, stocks_by_segment) for row in sorted_rows[:evidence_limit]]


def _row_to_evidence(
    row: _RowData,
    stocks_by_segment: dict[tuple[str, int], list[str]],
) -> AggregateTopicEvidence:
    return AggregateTopicEvidence(
        message_id=row["message_id"],
        message_time=datetime.fromisoformat(row["message_time"]),
        category=row["category"],
        classification_confidence=row["classification_confidence"],
        anchor_confidence=row["anchor_confidence"],
        sender=row["sender"],
        group_name=row["group_name"],
        raw_content=row["segment_text"] or row["raw_content"],
        stocks=stocks_by_segment.get(_segment_key(row), []),
    )


def _stocks_by_segment(
    rows: list[_RowData],
    noisy_segments: set[tuple[str, int]],
) -> dict[tuple[str, int], list[str]]:
    grouped: dict[tuple[str, int], list[str]] = defaultdict(list)
    seen: set[tuple[str, int, str]] = set()
    for row in rows:
        segment_key = _segment_key(row)
        if segment_key in noisy_segments:
            continue
        key = (*_segment_key(row), str(row["name"]))
        if key in seen:
            continue
        seen.add(key)
        grouped[(key[0], key[1])].append(key[2])
    return grouped


def _noisy_relation_segments(
    topic_rows: list[_RowData],
    stock_rows: list[_RowData],
) -> set[tuple[str, int]]:
    topic_names: dict[tuple[str, int], set[str]] = defaultdict(set)
    stock_names: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in topic_rows:
        topic_names[_segment_key(row)].add(str(row["name"]))
    for row in stock_rows:
        stock_names[_segment_key(row)].add(str(row["name"]))
    return {
        key
        for key, names in topic_names.items()
        if len(names) >= 3 and len(stock_names.get(key, set())) >= 2
    }


def _attach_segments(rows: list[sqlite3.Row]) -> list[_RowData]:
    segment_cache: dict[tuple[str, str], list] = {}
    enriched: list[_RowData] = []
    for row in rows:
        data = dict(row)
        cache_key = (str(data["message_id"]), str(data["raw_content"]))
        segments = segment_cache.get(cache_key)
        if segments is None:
            segments = split_text_segments(str(data["raw_content"]), max_segment_chars=_AGGREGATION_SEGMENT_CHARS)
            segment_cache[cache_key] = segments
        segment = segment_for_position(segments, _anchor_start(data.get("evidence_json")))
        data["segment_index"] = segment.index
        data["segment_text"] = segment.text
        enriched.append(data)
    return enriched


def _anchor_start(evidence_json: object) -> int | None:
    try:
        evidence = json.loads(str(evidence_json or "[]"))
    except json.JSONDecodeError:
        return None
    if not isinstance(evidence, list):
        return None
    for item in evidence:
        if isinstance(item, dict) and isinstance(item.get("start"), int):
            return item["start"]
    return None


def _segment_key(row: _RowData) -> tuple[str, int]:
    return (str(row["message_id"]), int(row.get("segment_index") or 0))


def _topic_key(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _anchor_type_order(anchor_type: str) -> int:
    return {"concept": 0, "theme": 1, "industry": 2}.get(anchor_type, 99)


def _validate_inputs(
    start_time: datetime,
    end_time: datetime,
    min_classification_confidence: float,
    min_messages: int,
    limit: int,
    evidence_limit: int,
) -> None:
    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if not 0 <= min_classification_confidence <= 1:
        raise ValueError("min_classification_confidence 必须在 0 到 1 之间")
    if min_messages < 1:
        raise ValueError("min_messages 必须大于 0")
    if limit < 1:
        raise ValueError("limit 必须大于 0")
    if evidence_limit < 0:
        raise ValueError("evidence_limit 不能小于 0")
