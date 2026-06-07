from __future__ import annotations

import sqlite3
import json
from datetime import datetime

from radar.core.usecases.source.models import SourceSignalCandidate, SourceSignalSnapshotItem, SourceSignalSnapshotPage, SourceStructure


def upsert_source_structures(conn: sqlite3.Connection, structures: list[SourceStructure]) -> int:
    if not structures:
        return 0
    rows = [
        (
            item.structure_id,
            item.message_id,
            item.source,
            item.sender,
            item.group_name,
            item.message_time.isoformat(),
            1 if item.is_candidate else 0,
            item.anchor_span,
            item.modifier_span,
            item.novel_span,
            item.relation_type,
            item.relation_evidence,
            item.ask_question,
            item.confidence,
            item.reject_reason,
            item.llm_provider,
            item.prompt_version,
            item.extractor_version,
            item.created_at.isoformat(),
            item.updated_at.isoformat(),
        )
        for item in structures
    ]
    before = conn.total_changes
    conn.executemany(
        """
        INSERT INTO source_structures (
            structure_id, message_id, source, sender, group_name, message_time,
            is_candidate, anchor_span, modifier_span, novel_span, relation_type,
            relation_evidence, ask_question, confidence, reject_reason, llm_provider,
            prompt_version, extractor_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id, anchor_span, modifier_span, novel_span, relation_type, extractor_version)
        DO UPDATE SET
            is_candidate=excluded.is_candidate,
            relation_evidence=excluded.relation_evidence,
            ask_question=excluded.ask_question,
            confidence=excluded.confidence,
            reject_reason=excluded.reject_reason,
            llm_provider=excluded.llm_provider,
            prompt_version=excluded.prompt_version,
            updated_at=excluded.updated_at
        """,
        rows,
    )
    conn.commit()
    return conn.total_changes - before


def list_source_structures(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    end_time: datetime,
    min_confidence: float = 0.65,
) -> list[SourceStructure]:
    rows = conn.execute(
        """
        SELECT *
        FROM source_structures
        WHERE message_time >= ?
          AND message_time <= ?
          AND is_candidate = 1
          AND confidence >= ?
        ORDER BY message_time ASC, structure_id ASC
        """,
        (start_time.isoformat(), end_time.isoformat(), min_confidence),
    ).fetchall()
    return [_structure_from_row(row) for row in rows]


def list_latest_source_signal_snapshots(
    conn: sqlite3.Connection,
    *,
    as_of_time: datetime | None = None,
    limit: int = 20,
) -> SourceSignalSnapshotPage:
    params: list[object] = []
    if as_of_time is None:
        asof_filter = "as_of_time = (SELECT MAX(as_of_time) FROM source_signal_snapshots)"
    else:
        asof_filter = "as_of_time = (SELECT MAX(as_of_time) FROM source_signal_snapshots WHERE as_of_time <= ?)"
        params.append(as_of_time.isoformat())
    params.append(limit)
    rows = conn.execute(
        f"""
        WITH ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY signal_id
                       ORDER BY created_at DESC, snapshot_id DESC
                   ) AS rn
            FROM source_signal_snapshots
            WHERE {asof_filter}
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
        ORDER BY
            CASE status
                WHEN 'spreading_watch' THEN 0
                WHEN 'mapped' THEN 1
                WHEN 'source_seed' THEN 2
                ELSE 9
            END,
            score DESC,
            first_seen_time ASC
        LIMIT ?
        """,
        params,
    ).fetchall()
    items = [_snapshot_from_row(row) for row in rows]
    return SourceSignalSnapshotPage(
        as_of_time=items[0].as_of_time if items else None,
        latest_created_at=max((item.created_at for item in items), default=None),
        item_count=len(items),
        available_as_of_times=list_source_signal_snapshot_times(conn),
        items=items,
    )


def list_source_signal_snapshot_times(conn: sqlite3.Connection, *, limit: int = 60) -> list[datetime]:
    rows = conn.execute(
        """
        SELECT as_of_time
        FROM source_signal_snapshots
        GROUP BY as_of_time
        ORDER BY as_of_time DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [datetime.fromisoformat(str(row["as_of_time"])) for row in rows]


def _structure_from_row(row: sqlite3.Row) -> SourceStructure:
    return SourceStructure(
        structure_id=str(row["structure_id"]),
        message_id=str(row["message_id"]),
        source=str(row["source"]),
        sender=str(row["sender"]),
        group_name=str(row["group_name"]) if row["group_name"] else None,
        message_time=datetime.fromisoformat(str(row["message_time"])),
        is_candidate=bool(row["is_candidate"]),
        anchor_span=str(row["anchor_span"]),
        modifier_span=str(row["modifier_span"]),
        novel_span=str(row["novel_span"]),
        relation_type=str(row["relation_type"]) if row["relation_type"] else "other",  # type: ignore[arg-type]
        relation_evidence=str(row["relation_evidence"]),
        ask_question=str(row["ask_question"]),
        confidence=float(row["confidence"] or 0),
        reject_reason=str(row["reject_reason"]) if row["reject_reason"] else None,
        llm_provider=str(row["llm_provider"]) if row["llm_provider"] else None,
        prompt_version=str(row["prompt_version"]),
        extractor_version=str(row["extractor_version"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _snapshot_from_row(row: sqlite3.Row) -> SourceSignalSnapshotItem:
    payload = json.loads(str(row["payload_json"]))
    candidate = SourceSignalCandidate.model_validate(payload)
    return SourceSignalSnapshotItem(
        **candidate.model_dump(),
        snapshot_id=str(row["snapshot_id"]),
        as_of_time=datetime.fromisoformat(str(row["as_of_time"])),
        created_at=datetime.fromisoformat(str(row["created_at"])),
    )
