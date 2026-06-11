from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from dataclasses import dataclass
from typing import Any

from radar.core.config import RadarConfig
from radar.core.storage.db import migrate_market_db
from radar.core.models import MessageSource
from radar.core.storage import connect
from radar.core.usecases.recommendation_backtest.models import BacktestAction, RecommendationEvent

RECOMMENDATION_EVENT_EXTRACTOR_VERSION = "lifecycle-evidence-v1"
_BEARISH_TERMS = ("卖出", "减仓", "看空", "规避", "回避", "下调评级", "降低评级", "谨慎")
_ACTION_TERMS = ("推荐", "强推", "强烈推荐", "重点推荐", "继续推荐", "首推", "call", "买入", "增持", "上调", "目标价")
_EMOJI_RE = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf\ufe0f]")
_ZERO_WIDTH_RE = re.compile("[\u200b-\u200f\u202a-\u202e]")
_SECTOR_ANCHOR_TYPES = ("industry", "concept", "theme")
_SECTOR_PRIORITY = {"industry": 3, "concept": 2, "theme": 1}
_CHUNK_SIZE = 500
_LIFECYCLE_EVENT_TYPES = {"调研", "报告", "路演", "催化", "扩散"}
_TYPE_CONFIDENCE = {"调研": 0.12, "报告": 0.14, "路演": 0.16, "催化": 0.15, "扩散": 0.10}


@dataclass(frozen=True)
class _AnalystIdentity:
    analyst_id: str
    display_name: str
    alias_text: str
    alias_key: str


@dataclass(frozen=True)
class _SectorAnchor:
    anchor_id: str
    anchor_type: str
    name: str
    confidence: float


@dataclass(frozen=True)
class _LifecycleEvidence:
    message_id: str
    ts_code: str
    stock_name: str
    judgement_confidence: float
    evidence_type: str
    stage: str
    evidence_text: str


def refresh_recommendation_events(
    config: RadarConfig,
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None = None,
    min_classification_confidence: float = 0.7,
    extractor_version: str = RECOMMENDATION_EVENT_EXTRACTOR_VERSION,
) -> tuple[list[RecommendationEvent], int]:
    """从个股证据链 LLM 认可的关键证据生成高质量回测事件。"""

    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if min_classification_confidence < 0 or min_classification_confidence > 1:
        raise ValueError("min_classification_confidence 必须在 0 到 1 之间")
    now = datetime.now()
    candidates = _lifecycle_evidence_candidates(conn, start_time=start_time, end_time=end_time)
    messages = _message_rows(conn, message_ids=sorted({item.message_id for item in candidates}))
    sectors = _stock_sectors(config, ts_codes=sorted({item.ts_code for item in candidates}), as_of=end_time)
    events = _events_from_lifecycle_evidence(
        candidates,
        messages=messages,
        sectors=sectors,
        start_time=start_time,
        end_time=end_time,
        source=source,
        min_classification_confidence=min_classification_confidence,
        now=now,
        extractor_version=extractor_version,
    )
    _upsert_analysts(conn, events, now=now)
    inserted = _upsert_events(conn, events)
    return events, inserted


def list_recommendation_events(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None = None,
    extractor_version: str = RECOMMENDATION_EVENT_EXTRACTOR_VERSION,
) -> list[RecommendationEvent]:
    where = ["message_time >= ?", "message_time < ?", "extractor_version = ?"]
    params: list[Any] = [start_time.isoformat(), end_time.isoformat(), extractor_version]
    if source:
        where.append("source = ?")
        params.append(source)
    rows = conn.execute(
        f"""
        SELECT * FROM recommendation_events
        WHERE {" AND ".join(where)}
        ORDER BY message_time ASC, event_id ASC
        """,
        params,
    ).fetchall()
    return [_event_from_row(row) for row in rows]


def _lifecycle_evidence_candidates(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
) -> list[_LifecycleEvidence]:
    rows = conn.execute(
        """
        SELECT ts_code, stock_name, stage, confidence, result_json, evidence_refs_json
        FROM stock_lifecycle_judgements
        WHERE as_of_time >= ?
          AND as_of_time <= ?
        ORDER BY as_of_time DESC, updated_at DESC
        """,
        (start_time.isoformat(), end_time.isoformat()),
    ).fetchall()
    by_key: dict[tuple[str, str], _LifecycleEvidence] = {}
    for row in rows:
        result = _json_dict(row["result_json"])
        refs = _evidence_ref_ids(row["evidence_refs_json"])
        confidence = _float(row["confidence"]) or _float(result.get("confidence")) or 0.65
        for point in _json_list(result.get("evidence_chain")):
            if not isinstance(point, dict):
                continue
            message_id = str(point.get("message_id") or "")
            evidence_type = str(point.get("type") or "").strip()
            if not message_id or message_id not in refs or not _is_lifecycle_event_type(evidence_type):
                continue
            item = _LifecycleEvidence(
                message_id=message_id,
                ts_code=str(row["ts_code"]),
                stock_name=str(row["stock_name"]),
                judgement_confidence=confidence,
                evidence_type=evidence_type,
                stage=str(row["stage"]),
                evidence_text=str(point.get("evidence") or ""),
            )
            key = (message_id, item.ts_code)
            old = by_key.get(key)
            if old is None or _lifecycle_score(item) > _lifecycle_score(old):
                by_key[key] = item
    return list(by_key.values())


def _message_rows(conn: sqlite3.Connection, *, message_ids: list[str]) -> dict[str, sqlite3.Row]:
    result: dict[str, sqlite3.Row] = {}
    for chunk in _chunks(message_ids, _CHUNK_SIZE):
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT
                m.message_id, m.source, m.sender, m.group_name, m.message_time, m.raw_content,
                COALESCE(c.category, 'research') AS category,
                COALESCE(c.confidence, 1.0) AS classification_confidence
            FROM messages m
            LEFT JOIN message_classifications c ON c.message_id = m.message_id
            WHERE m.message_id IN ({placeholders})
            """,
            chunk,
        ).fetchall()
        for row in rows:
            result[str(row["message_id"])] = row
    return result


def _events_from_lifecycle_evidence(
    candidates: list[_LifecycleEvidence],
    *,
    messages: dict[str, sqlite3.Row],
    sectors: dict[str, _SectorAnchor],
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None,
    min_classification_confidence: float,
    now: datetime,
    extractor_version: str,
) -> list[RecommendationEvent]:
    by_key: dict[tuple[str, str, BacktestAction], RecommendationEvent] = {}
    for item in candidates:
        row = messages.get(item.message_id)
        if row is None:
            continue
        message_time = datetime.fromisoformat(str(row["message_time"]))
        if message_time < start_time or message_time >= end_time:
            continue
        if source and row["source"] != source:
            continue
        classification_confidence = float(row["classification_confidence"] or 0)
        if classification_confidence < min_classification_confidence:
            continue
        raw_content = str(row["raw_content"] or "")
        action = _infer_action(raw_content)
        source_candidate = _source_candidate(str(row["sender"]))
        analyst = _analyst_identity(source_candidate)
        sector = sectors.get(item.ts_code)
        event = RecommendationEvent(
            event_id=_event_id(item.message_id, item.ts_code, action, extractor_version),
            message_id=item.message_id,
            source=str(row["source"]),
            source_candidate=source_candidate,
            analyst_id=analyst.analyst_id,
            analyst_display_name=analyst.display_name,
            analyst_alias_key=analyst.alias_key,
            group_name=row["group_name"],
            category=str(row["category"] or _category_for_type(item.evidence_type)),
            classification_confidence=classification_confidence,
            ts_code=item.ts_code,
            stock_name=item.stock_name,
            action=action,
            message_time=message_time,
            event_date=message_time.strftime("%Y%m%d"),
            extractor_version=extractor_version,
            anchor_confidence=_anchor_confidence(item, raw_content),
            sector_anchor_id=sector.anchor_id if sector else None,
            sector_anchor_type=sector.anchor_type if sector else None,
            sector_name=sector.name if sector else None,
            sector_confidence=sector.confidence if sector else None,
            created_at=now,
            updated_at=now,
        )
        key = (event.message_id, event.ts_code, event.action)
        old = by_key.get(key)
        if old is None or event.anchor_confidence > old.anchor_confidence:
            by_key[key] = event
    return sorted(by_key.values(), key=lambda event: (event.message_time, event.event_id))


def _stock_sectors(config: RadarConfig, *, ts_codes: list[str], as_of: datetime) -> dict[str, _SectorAnchor]:
    if not ts_codes:
        return {}
    market_conn = connect(config.market_database_path)
    try:
        migrate_market_db(market_conn)
        result: dict[str, _SectorAnchor] = {}
        for chunk in _chunks(ts_codes, _CHUNK_SIZE):
            placeholders = ", ".join("?" for _ in chunk)
            rows = market_conn.execute(
                f"""
                SELECT
                    mam.ts_code, ma.anchor_id, ma.anchor_type, ma.name,
                    COALESCE(ma.hot_score, 0) AS hot_score, ma.trade_date
                FROM market_anchor_members mam
                JOIN market_anchors ma ON ma.anchor_id = mam.anchor_id
                WHERE mam.ts_code IN ({placeholders})
                  AND mam.trade_date = ma.trade_date
                  AND ma.trade_date <= ?
                  AND ma.anchor_type IN ('industry', 'concept', 'theme')
                """,
                [*chunk, as_of.strftime("%Y%m%d")],
            ).fetchall()
            for row in sorted(rows, key=_sector_row_sort_key, reverse=True):
                ts_code = str(row["ts_code"])
                if ts_code in result:
                    continue
                result[ts_code] = _SectorAnchor(
                    anchor_id=str(row["anchor_id"]),
                    anchor_type=str(row["anchor_type"]),
                    name=str(row["name"]),
                    confidence=min(0.95, 0.72 + float(row["hot_score"] or 0) / 1000),
                )
        return result
    finally:
        market_conn.close()


def _upsert_analysts(conn: sqlite3.Connection, events: list[RecommendationEvent], *, now: datetime) -> None:
    identities: dict[str, _AnalystIdentity] = {}
    for event in events:
        if not event.analyst_id or not event.analyst_display_name or not event.analyst_alias_key:
            continue
        identities[event.source_candidate] = _AnalystIdentity(
            analyst_id=event.analyst_id,
            display_name=event.analyst_display_name,
            alias_text=event.source_candidate,
            alias_key=event.analyst_alias_key,
        )
    if not identities:
        return

    rows = list(identities.values())
    conn.executemany(
        """
        INSERT INTO analysts (analyst_id, display_name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(analyst_id) DO UPDATE SET
            updated_at = excluded.updated_at
        """,
        [(row.analyst_id, row.display_name, now.isoformat(), now.isoformat()) for row in rows],
    )
    conn.executemany(
        """
        INSERT INTO analyst_aliases (
            alias_text, alias_key, analyst_id, confidence, method, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(alias_text) DO UPDATE SET
            alias_key = excluded.alias_key,
            analyst_id = excluded.analyst_id,
            confidence = excluded.confidence,
            method = excluded.method,
            updated_at = excluded.updated_at
        """,
        [
            (
                row.alias_text,
                row.alias_key,
                row.analyst_id,
                0.9,
                "normalized_sender",
                now.isoformat(),
                now.isoformat(),
            )
            for row in rows
        ],
    )


def _upsert_events(conn: sqlite3.Connection, events: list[RecommendationEvent]) -> int:
    if not events:
        return 0

    existing_ids = {
        str(row[0])
        for row in conn.execute(
            f"SELECT event_id FROM recommendation_events WHERE event_id IN ({', '.join('?' for _ in events)})",
            [event.event_id for event in events],
        ).fetchall()
    }
    conn.executemany(
        """
        INSERT INTO recommendation_events (
            event_id, message_id, source, source_candidate, group_name, category,
            classification_confidence, ts_code, stock_name, action, message_time,
            event_date, extractor_version, anchor_confidence, analyst_id,
            analyst_display_name, analyst_alias_key, sector_anchor_id,
            sector_anchor_type, sector_name, sector_confidence, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            source = excluded.source,
            source_candidate = excluded.source_candidate,
            analyst_id = excluded.analyst_id,
            analyst_display_name = excluded.analyst_display_name,
            analyst_alias_key = excluded.analyst_alias_key,
            group_name = excluded.group_name,
            category = excluded.category,
            classification_confidence = excluded.classification_confidence,
            stock_name = excluded.stock_name,
            message_time = excluded.message_time,
            event_date = excluded.event_date,
            anchor_confidence = excluded.anchor_confidence,
            sector_anchor_id = excluded.sector_anchor_id,
            sector_anchor_type = excluded.sector_anchor_type,
            sector_name = excluded.sector_name,
            sector_confidence = excluded.sector_confidence,
            updated_at = excluded.updated_at
        """,
        [
            (
                event.event_id,
                event.message_id,
                event.source,
                event.source_candidate,
                event.group_name,
                event.category,
                event.classification_confidence,
                event.ts_code,
                event.stock_name,
                event.action,
                event.message_time.isoformat(),
                event.event_date,
                event.extractor_version,
                event.anchor_confidence,
                event.analyst_id,
                event.analyst_display_name,
                event.analyst_alias_key,
                event.sector_anchor_id,
                event.sector_anchor_type,
                event.sector_name,
                event.sector_confidence,
                event.created_at.isoformat(),
                event.updated_at.isoformat(),
            )
            for event in events
        ],
    )
    conn.commit()
    return len(set(event.event_id for event in events) - existing_ids)


def _event_from_row(row: sqlite3.Row) -> RecommendationEvent:
    return RecommendationEvent(
        event_id=row["event_id"],
        message_id=row["message_id"],
        source=row["source"],
        source_candidate=row["source_candidate"],
        analyst_id=row["analyst_id"],
        analyst_display_name=row["analyst_display_name"],
        analyst_alias_key=row["analyst_alias_key"],
        group_name=row["group_name"],
        category=row["category"],
        classification_confidence=row["classification_confidence"],
        ts_code=row["ts_code"],
        stock_name=row["stock_name"],
        action=row["action"],
        message_time=datetime.fromisoformat(row["message_time"]),
        event_date=row["event_date"],
        extractor_version=row["extractor_version"],
        anchor_confidence=row["anchor_confidence"],
        sector_anchor_id=row["sector_anchor_id"],
        sector_anchor_type=row["sector_anchor_type"],
        sector_name=row["sector_name"],
        sector_confidence=row["sector_confidence"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _is_lifecycle_event_type(value: str) -> bool:
    if value in _LIFECYCLE_EVENT_TYPES:
        return True
    return value == "其他"


def _lifecycle_score(item: _LifecycleEvidence) -> float:
    return item.judgement_confidence + _TYPE_CONFIDENCE.get(item.evidence_type, 0)


def _anchor_confidence(item: _LifecycleEvidence, raw_content: str) -> float:
    action_bonus = 0.08 if any(term.lower() in raw_content.lower() for term in _ACTION_TERMS) else 0
    value = item.judgement_confidence * 0.72 + _TYPE_CONFIDENCE.get(item.evidence_type, 0.04) + action_bonus
    return round(min(max(value, 0.01), 0.99), 4)


def _category_for_type(value: str) -> str:
    if value in {"报告", "调研"}:
        return "research"
    if value == "路演":
        return "event"
    return "recommendation"


def _sector_row_sort_key(row: sqlite3.Row) -> tuple[str, int, float, str]:
    return (
        str(row["trade_date"]),
        _SECTOR_PRIORITY.get(str(row["anchor_type"]), 0),
        float(row["hot_score"] or 0),
        str(row["name"]),
    )


def _evidence_ref_ids(value: object) -> set[str]:
    return {str(item.get("message_id") or "") for item in _json_list(value) if isinstance(item, dict)}


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


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _infer_action(raw_content: str) -> BacktestAction:
    # 第一版只做粗方向，复杂的一条消息多标的不同动作后续再进结构化抽取。
    if any(term in raw_content for term in _BEARISH_TERMS):
        return "bearish"
    return "bullish"


def _source_candidate(sender: str) -> str:
    value = " ".join(sender.split())
    return value or "未知来源"


def _analyst_identity(source_candidate: str) -> _AnalystIdentity:
    alias_key = _alias_key(source_candidate)
    raw = f"analyst|{alias_key}"
    return _AnalystIdentity(
        analyst_id="an_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16],
        display_name=source_candidate,
        alias_text=source_candidate,
        alias_key=alias_key,
    )


def _alias_key(source_candidate: str) -> str:
    value = unicodedata.normalize("NFKC", source_candidate)
    value = _EMOJI_RE.sub("", value)
    value = _ZERO_WIDTH_RE.sub("", value)
    value = "".join(value.split())
    return value or "未知来源"


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _event_id(message_id: str, ts_code: str, action: BacktestAction, extractor_version: str) -> str:
    raw = f"{message_id}|{ts_code}|{action}|{extractor_version}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
