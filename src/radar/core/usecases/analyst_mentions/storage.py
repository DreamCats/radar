from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from radar.core.models import MessageSource
from radar.core.usecases.analyst_mentions.identity import analyst_identity
from radar.core.usecases.analyst_mentions.models import AnalystMentionEvent


def replace_mentions(
    conn: sqlite3.Connection,
    mentions: list[AnalystMentionEvent],
    *,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None,
    extractor_version: str,
) -> None:
    where = ["message_time >= ?", "message_time < ?", "extractor_version = ?"]
    params: list[Any] = [start_time.isoformat(), end_time.isoformat(), extractor_version]
    if source:
        where.append("source = ?")
        params.append(source)
    rows = conn.execute(
        f"SELECT mention_id FROM analyst_stock_mentions WHERE {' AND '.join(where)}",
        params,
    ).fetchall()
    old_ids = [str(row["mention_id"]) for row in rows]
    for chunk in _chunks(old_ids, 500):
        placeholders = ", ".join("?" for _ in chunk)
        conn.execute(
            f"DELETE FROM analyst_stock_mention_windows WHERE mention_id IN ({placeholders})",
            chunk,
        )
        conn.execute(
            f"DELETE FROM analyst_stock_mentions WHERE mention_id IN ({placeholders})",
            chunk,
        )
    if mentions:
        conn.executemany(
            """
            INSERT INTO analyst_stock_mentions (
                mention_id, message_id, source, sender, analyst_id, analyst_display_name,
                analyst_alias_key, group_name, category, classification_confidence,
                ts_code, stock_name, symbol, message_time, event_date, evidence_snippet,
                content_fingerprint, extractor_version, stock_count_in_message,
                quality_flags, is_effective, dedupe_key, dedupe_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [_mention_values(item) for item in mentions],
        )
    conn.commit()


def upsert_analysts(conn: sqlite3.Connection, mentions: list[AnalystMentionEvent]) -> None:
    now = datetime.now().isoformat()
    identities = {item.sender: analyst_identity(item.sender) for item in mentions}
    if not identities:
        return
    conn.executemany(
        """
        INSERT INTO analysts (analyst_id, display_name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(analyst_id) DO UPDATE SET updated_at = excluded.updated_at
        """,
        [(item.analyst_id, item.display_name, now, now) for item in identities.values()],
    )
    conn.executemany(
        """
        INSERT INTO analyst_aliases (
            alias_text, alias_key, analyst_id, confidence, method, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(alias_text) DO UPDATE SET
            alias_key = excluded.alias_key,
            analyst_id = excluded.analyst_id,
            confidence = excluded.confidence,
            method = excluded.method,
            updated_at = excluded.updated_at
        """,
        [
            (name, item.alias_key, item.analyst_id, 0.9, "normalized_sender", now, now)
            for name, item in identities.items()
        ],
    )
    conn.commit()


def _mention_values(item: AnalystMentionEvent) -> tuple[object, ...]:
    return (
        item.mention_id,
        item.message_id,
        item.source,
        item.sender,
        item.analyst_id,
        item.analyst_display_name,
        item.analyst_alias_key,
        item.group_name,
        item.category,
        item.classification_confidence,
        item.ts_code,
        item.stock_name,
        item.symbol,
        item.message_time.isoformat(),
        item.event_date,
        item.evidence_snippet,
        item.content_fingerprint,
        item.extractor_version,
        item.stock_count_in_message,
        json.dumps(list(item.quality_flags), ensure_ascii=False),
        int(item.is_effective),
        item.dedupe_key,
        item.dedupe_reason,
        item.created_at.isoformat(),
        item.updated_at.isoformat(),
    )


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]
