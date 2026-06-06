from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from datetime import datetime
from dataclasses import dataclass
from typing import Any

from radar.core.models import MessageSource
from radar.core.usecases.anchoring import ANCHOR_EXTRACTOR_VERSION
from radar.core.usecases.recommendation_backtest.models import BacktestAction, RecommendationEvent

_TS_CODE_RE = re.compile(r"^stock:(\d{6}\.(?:SH|SZ|BJ))$", re.IGNORECASE)
_BEARISH_TERMS = ("卖出", "减仓", "看空", "规避", "回避", "下调评级", "降低评级", "谨慎")
_EMOJI_RE = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf\ufe0f]")
_ZERO_WIDTH_RE = re.compile("[\u200b-\u200f\u202a-\u202e]")
_SECTOR_ANCHOR_TYPES = ("industry", "concept", "theme")
_SECTOR_PRIORITY = {"industry": 3, "concept": 2, "theme": 1}
_CHUNK_SIZE = 500


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


def refresh_recommendation_events(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None = None,
    min_classification_confidence: float = 0.7,
    extractor_version: str = ANCHOR_EXTRACTOR_VERSION,
) -> tuple[list[RecommendationEvent], int]:
    """把 recommendation+stock anchor 固化成回测事件，不保存消息原文。"""

    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if min_classification_confidence < 0 or min_classification_confidence > 1:
        raise ValueError("min_classification_confidence 必须在 0 到 1 之间")

    now = datetime.now()
    candidates = _candidate_rows(
        conn,
        start_time=start_time,
        end_time=end_time,
        source=source,
        min_classification_confidence=min_classification_confidence,
        extractor_version=extractor_version,
    )
    sectors = _primary_sectors(
        conn,
        message_ids=[str(row["message_id"]) for row in candidates],
        extractor_version=extractor_version,
    )
    events = _dedupe_events(candidates, sectors=sectors, now=now, extractor_version=extractor_version)
    _upsert_analysts(conn, events, now=now)
    inserted = _upsert_events(conn, events)
    return events, inserted


def list_recommendation_events(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None = None,
) -> list[RecommendationEvent]:
    where = ["message_time >= ?", "message_time < ?"]
    params: list[Any] = [start_time.isoformat(), end_time.isoformat()]
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


def _candidate_rows(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None,
    min_classification_confidence: float,
    extractor_version: str,
) -> list[sqlite3.Row]:
    where = [
        "c.category = 'recommendation'",
        "c.status != 'ignored'",
        "c.confidence >= ?",
        "a.anchor_type = 'stock'",
        "a.extractor_version = ?",
        "m.message_time >= ?",
        "m.message_time < ?",
    ]
    params: list[Any] = [
        min_classification_confidence,
        extractor_version,
        start_time.isoformat(),
        end_time.isoformat(),
    ]
    if source:
        where.append("m.source = ?")
        params.append(source)
    return conn.execute(
        f"""
        SELECT
            m.message_id, m.source, m.sender, m.group_name, m.message_time, m.raw_content,
            c.category, c.confidence AS classification_confidence,
            a.anchor_id, a.name AS stock_name, a.confidence AS anchor_confidence
        FROM messages m
        JOIN message_classifications c ON c.message_id = m.message_id
        JOIN message_anchors a ON a.message_id = m.message_id
        WHERE {" AND ".join(where)}
        ORDER BY m.message_time ASC, a.confidence DESC
        """,
        params,
    ).fetchall()


def _dedupe_events(
    rows: list[sqlite3.Row],
    *,
    sectors: dict[str, _SectorAnchor],
    now: datetime,
    extractor_version: str,
) -> list[RecommendationEvent]:
    by_key: dict[tuple[str, str, BacktestAction], RecommendationEvent] = {}
    for row in rows:
        ts_code = _ts_code_from_anchor(str(row["anchor_id"]))
        if ts_code is None:
            continue
        action = _infer_action(str(row["raw_content"] or ""))
        key = (str(row["message_id"]), ts_code, action)
        event = _event_from_candidate(
            row,
            ts_code,
            action,
            sector=sectors.get(str(row["message_id"])),
            now=now,
            extractor_version=extractor_version,
        )
        old = by_key.get(key)
        if old is None or event.anchor_confidence > old.anchor_confidence:
            by_key[key] = event
    return list(by_key.values())


def _event_from_candidate(
    row: sqlite3.Row,
    ts_code: str,
    action: BacktestAction,
    *,
    sector: _SectorAnchor | None,
    now: datetime,
    extractor_version: str,
) -> RecommendationEvent:
    message_time = datetime.fromisoformat(str(row["message_time"]))
    source_candidate = _source_candidate(str(row["sender"]))
    analyst = _analyst_identity(source_candidate)
    return RecommendationEvent(
        event_id=_event_id(str(row["message_id"]), ts_code, action, extractor_version),
        message_id=str(row["message_id"]),
        source=str(row["source"]),
        source_candidate=source_candidate,
        analyst_id=analyst.analyst_id,
        analyst_display_name=analyst.display_name,
        analyst_alias_key=analyst.alias_key,
        group_name=row["group_name"],
        category=str(row["category"]),
        classification_confidence=float(row["classification_confidence"]),
        ts_code=ts_code,
        stock_name=str(row["stock_name"]),
        action=action,
        message_time=message_time,
        event_date=message_time.strftime("%Y%m%d"),
        extractor_version=extractor_version,
        anchor_confidence=float(row["anchor_confidence"]),
        sector_anchor_id=sector.anchor_id if sector else None,
        sector_anchor_type=sector.anchor_type if sector else None,
        sector_name=sector.name if sector else None,
        sector_confidence=sector.confidence if sector else None,
        created_at=now,
        updated_at=now,
    )


def _primary_sectors(
    conn: sqlite3.Connection,
    *,
    message_ids: list[str],
    extractor_version: str,
) -> dict[str, _SectorAnchor]:
    ids = sorted(set(message_ids))
    if not ids:
        return {}

    sectors: dict[str, _SectorAnchor] = {}
    type_placeholders = ", ".join("?" for _ in _SECTOR_ANCHOR_TYPES)
    for chunk in _chunks(ids, _CHUNK_SIZE):
        id_placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT message_id, anchor_id, anchor_type, name, confidence
            FROM message_anchors
            WHERE extractor_version = ?
              AND anchor_type IN ({type_placeholders})
              AND message_id IN ({id_placeholders})
            """,
            [extractor_version, *_SECTOR_ANCHOR_TYPES, *chunk],
        ).fetchall()
        for row in rows:
            sector = _SectorAnchor(
                anchor_id=str(row["anchor_id"]),
                anchor_type=str(row["anchor_type"]),
                name=str(row["name"]),
                confidence=float(row["confidence"]),
            )
            old = sectors.get(str(row["message_id"]))
            if old is None or _sector_sort_key(sector) > _sector_sort_key(old):
                sectors[str(row["message_id"])] = sector
    return sectors


def _sector_sort_key(sector: _SectorAnchor) -> tuple[float, int, str]:
    return sector.confidence, _SECTOR_PRIORITY.get(sector.anchor_type, 0), sector.name


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


def _ts_code_from_anchor(anchor_id: str) -> str | None:
    match = _TS_CODE_RE.match(anchor_id)
    return match.group(1).upper() if match else None


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
