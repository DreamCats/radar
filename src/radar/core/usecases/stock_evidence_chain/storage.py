from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from radar.core.filtering import is_group_blacklisted
from radar.core.usecases.stock_evidence_chain.models import (
    HIGH_VALUE_CATEGORIES,
    EvidencePack,
    MessageRow,
    Stock,
    StockCandidate,
    StockMention,
)

WATCH_FILL_TARGET = 50
WATCH_CHANNEL = "watch"


def load_messages(
    conn: sqlite3.Connection,
    *,
    start: datetime,
    end: datetime,
    blacklist_patterns: list[str],
    categories: tuple[str, ...] = HIGH_VALUE_CATEGORIES,
    matcher_version: str | None = None,
    force: bool = False,
) -> list[MessageRow]:
    placeholders = ", ".join("?" for _ in categories)
    joins = ["JOIN message_classifications c ON c.message_id = m.message_id"]
    join_params: list[object] = []
    where = [
        "m.message_time >= ?",
        "m.message_time <= ?",
        f"c.category IN ({placeholders})",
        "c.status != 'ignored'",
    ]
    where_params: list[object] = [start.isoformat(), end.isoformat(), *categories]
    if matcher_version and not force:
        joins.append(
            """
            LEFT JOIN stock_mention_status sms
              ON sms.message_id = m.message_id
             AND sms.matcher_version = ?
            """
        )
        join_params.append(matcher_version)
        where.append("sms.message_id IS NULL")
    rows = conn.execute(
        f"""
        SELECT m.message_id, m.source, m.sender, m.message_time, m.raw_content, m.group_name, c.category
        FROM messages m
        {' '.join(joins)}
        WHERE {' AND '.join(where)}
        ORDER BY m.message_time ASC, m.message_id ASC
        """,
        [*join_params, *where_params],
    ).fetchall()
    messages = [_row_to_message(row) for row in rows]
    return [row for row in messages if not is_group_blacklisted(row.group_name, blacklist_patterns)]


def upsert_mentions(conn: sqlite3.Connection, mentions: list[StockMention]) -> int:
    now = datetime.now().isoformat()
    changed = 0
    for mention in mentions:
        row = conn.execute(
            """
            INSERT INTO stock_message_mentions (
                message_id, ts_code, stock_name, symbol, message_time, source, sender, group_name,
                category, fingerprint, evidence_score, evidence_families_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id, ts_code) DO UPDATE SET
                stock_name = excluded.stock_name,
                symbol = excluded.symbol,
                message_time = excluded.message_time,
                source = excluded.source,
                sender = excluded.sender,
                group_name = excluded.group_name,
                category = excluded.category,
                fingerprint = excluded.fingerprint,
                evidence_score = excluded.evidence_score,
                evidence_families_json = excluded.evidence_families_json,
                updated_at = excluded.updated_at
            """,
            (
                mention.message.message_id,
                mention.stock.ts_code,
                mention.stock.name,
                mention.stock.symbol,
                mention.message.message_time.isoformat(),
                mention.message.source,
                mention.message.sender,
                mention.message.group_name,
                mention.message.category,
                mention.fingerprint,
                mention.evidence_score,
                json.dumps(list(mention.evidence_families), ensure_ascii=False),
                now,
                now,
            ),
        )
        changed += row.rowcount
    conn.commit()
    return changed


def delete_mentions_for_messages(conn: sqlite3.Connection, messages: list[MessageRow]) -> None:
    if not messages:
        return
    message_ids = [message.message_id for message in messages]
    for start in range(0, len(message_ids), 500):
        chunk = message_ids[start : start + 500]
        placeholders = ", ".join("?" for _ in chunk)
        conn.execute(f"DELETE FROM stock_message_mentions WHERE message_id IN ({placeholders})", chunk)
    conn.commit()


def mark_indexed(
    conn: sqlite3.Connection,
    *,
    messages: list[MessageRow],
    mention_counts: dict[str, int],
    matcher_version: str,
) -> None:
    now = datetime.now().isoformat()
    for message in messages:
        conn.execute(
            """
            INSERT INTO stock_mention_status (message_id, matcher_version, mention_count, indexed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                matcher_version = excluded.matcher_version,
                mention_count = excluded.mention_count,
                indexed_at = excluded.indexed_at
            """,
            (message.message_id, matcher_version, mention_counts.get(message.message_id, 0), now),
        )
    conn.commit()


def load_candidates(conn: sqlite3.Connection, *, window_start: datetime, as_of: datetime) -> list[StockCandidate]:
    rows = conn.execute(
        """
        SELECT *
        FROM stock_message_mentions
        WHERE message_time >= ? AND message_time <= ?
        ORDER BY message_time ASC, message_id ASC
        """,
        (window_start.isoformat(), as_of.isoformat()),
    ).fetchall()
    by_code: dict[str, StockCandidate] = {}
    for row in rows:
        stock = Stock(ts_code=str(row["ts_code"]), symbol=str(row["symbol"]), name=str(row["stock_name"]))
        item = by_code.setdefault(stock.ts_code, StockCandidate(stock=stock))
        item.trigger_count += 1
        item.unique_fingerprints.add(str(row["fingerprint"]))
        item.senders.add(str(row["sender"]))
        item.conversations.add(str(row["group_name"] or row["sender"]))
        item.evidence_score += int(row["evidence_score"] or 0)
        for family in json.loads(str(row["evidence_families_json"] or "[]")):
            item.family_counts[family] = item.family_counts.get(family, 0) + 1
    for item in by_code.values():
        if item.unique_trigger_count >= 7:
            item.channels.add("heat")
        if _is_early_strong(item):
            item.channels.add("early_strong")
    strong_candidates = [item for item in by_code.values() if item.channels]
    if len(strong_candidates) < WATCH_FILL_TARGET:
        watch_candidates = sorted(
            (item for item in by_code.values() if not item.channels and _is_watch_candidate(item)),
            key=lambda item: item.rank_key,
            reverse=True,
        )[: WATCH_FILL_TARGET - len(strong_candidates)]
        for item in watch_candidates:
            item.channels.add(WATCH_CHANNEL)
    return sorted((item for item in by_code.values() if item.channels), key=lambda item: item.rank_key, reverse=True)


def load_evidence_pack(
    conn: sqlite3.Connection,
    *,
    candidate: StockCandidate,
    window_start: datetime,
    evidence_start: datetime,
    as_of: datetime,
    max_items: int,
) -> EvidencePack:
    rows = conn.execute(
        """
        SELECT smm.*, m.raw_content
        FROM stock_message_mentions smm
        JOIN messages m ON m.message_id = smm.message_id
        WHERE smm.ts_code = ?
          AND smm.message_time >= ?
          AND smm.message_time <= ?
        ORDER BY smm.message_time ASC, smm.message_id ASC
        """,
        (candidate.stock.ts_code, evidence_start.isoformat(), as_of.isoformat()),
    ).fetchall()
    historical: list[StockMention] = []
    current: list[StockMention] = []
    seen: set[str] = set()
    for row in rows:
        fingerprint = str(row["fingerprint"])
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        mention = _row_to_mention(row)
        if mention.message.message_time >= window_start:
            current.append(mention)
        else:
            historical.append(mention)
    if len(current) >= max_items:
        evidence = current[:max_items]
    else:
        evidence = historical[: max_items - len(current)] + current
    evidence = sorted(evidence, key=lambda item: (item.message.message_time, item.message.message_id))
    return EvidencePack(candidate=candidate, evidence=evidence)


def save_candidates(
    conn: sqlite3.Connection,
    *,
    as_of: datetime,
    window_start: datetime,
    evidence_start: datetime,
    candidates: list[StockCandidate],
) -> None:
    now = datetime.now().isoformat()
    existing_count = conn.execute(
        "SELECT COUNT(*) FROM stock_lifecycle_candidates WHERE as_of_time = ?",
        (as_of.isoformat(),),
    ).fetchone()[0]
    # 小 limit 复跑常用于抽样 LLM 判断，不能把同一天已有的完整候选池裁掉。
    if existing_count <= len(candidates):
        conn.execute("DELETE FROM stock_lifecycle_candidates WHERE as_of_time = ?", (as_of.isoformat(),))
    for index, item in enumerate(candidates, start=1):
        conn.execute(
            """
            INSERT INTO stock_lifecycle_candidates (
                as_of_time, window_start_time, evidence_start_time, ts_code, stock_name,
                trigger_count, unique_trigger_count, sender_count, conversation_count,
                evidence_score, channels_json, family_counts_json, rank, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(as_of_time, ts_code) DO UPDATE SET
                trigger_count = excluded.trigger_count,
                unique_trigger_count = excluded.unique_trigger_count,
                sender_count = excluded.sender_count,
                conversation_count = excluded.conversation_count,
                evidence_score = excluded.evidence_score,
                channels_json = excluded.channels_json,
                family_counts_json = excluded.family_counts_json,
                rank = excluded.rank
            """,
            (
                as_of.isoformat(),
                window_start.isoformat(),
                evidence_start.isoformat(),
                item.stock.ts_code,
                item.stock.name,
                item.trigger_count,
                item.unique_trigger_count,
                item.sender_count,
                item.conversation_count,
                item.evidence_score,
                json.dumps(sorted(item.channels), ensure_ascii=False),
                json.dumps(item.family_counts, ensure_ascii=False, sort_keys=True),
                index,
                now,
            ),
        )
    conn.commit()


def _is_early_strong(item: StockCandidate) -> bool:
    if item.unique_trigger_count < 3 or item.sender_count < 2 or item.conversation_count < 2:
        return False
    return item.family_counts.get("catalyst", 0) > 0 or item.evidence_score >= 8


def _is_watch_candidate(item: StockCandidate) -> bool:
    if item.unique_trigger_count < 2 or item.sender_count < 2 or item.conversation_count < 2:
        return False
    return item.family_counts.get("catalyst", 0) > 0 or item.evidence_score >= 8


def _row_to_message(row: sqlite3.Row) -> MessageRow:
    return MessageRow(
        message_id=str(row["message_id"]),
        source=str(row["source"]),
        sender=str(row["sender"]),
        message_time=datetime.fromisoformat(str(row["message_time"])),
        raw_content=str(row["raw_content"]),
        group_name=str(row["group_name"]) if row["group_name"] else None,
        category=str(row["category"]) if row["category"] else None,
    )


def _row_to_mention(row: sqlite3.Row) -> StockMention:
    message = MessageRow(
        message_id=str(row["message_id"]),
        source=str(row["source"]),
        sender=str(row["sender"]),
        message_time=datetime.fromisoformat(str(row["message_time"])),
        raw_content=str(row["raw_content"]),
        group_name=str(row["group_name"]) if row["group_name"] else None,
        category=str(row["category"]) if row["category"] else None,
    )
    stock = Stock(ts_code=str(row["ts_code"]), symbol=str(row["symbol"]), name=str(row["stock_name"]))
    return StockMention(
        stock=stock,
        message=message,
        fingerprint=str(row["fingerprint"]),
        evidence_families=tuple(json.loads(str(row["evidence_families_json"] or "[]"))),
        evidence_score=int(row["evidence_score"] or 0),
    )
