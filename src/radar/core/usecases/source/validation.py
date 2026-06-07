from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from radar.core.config import RadarConfig
from radar.core.db import migrate_message_db
from radar.core.store import connect
from radar.core.usecases.source.models import (
    SourceSignalCandidate,
    SourceSignalValidationMetric,
    SourceSignalValidationRow,
    SourceSignalValidationSummary,
)


def summarize_source_signal_validation(
    config: RadarConfig,
    *,
    window_days: int = 5,
    limit: int = 12,
) -> SourceSignalValidationSummary:
    with connect(config.database_path) as conn:
        migrate_message_db(conn)
        return summarize_source_signal_validation_from_conn(conn, window_days=window_days, limit=limit)


def summarize_source_signal_validation_from_conn(
    conn: sqlite3.Connection,
    *,
    window_days: int,
    limit: int = 12,
) -> SourceSignalValidationSummary:
    rows = conn.execute(
        """
        SELECT signal_id, status, as_of_time, score, payload_json
        FROM source_signal_snapshots
        ORDER BY signal_id, as_of_time ASC, created_at ASC
        """
    ).fetchall()
    snapshot_count = _count_snapshots(conn)
    latest_snapshot_time = _latest_snapshot_time(conn)
    histories: dict[str, list[_HistoryPoint]] = defaultdict(list)
    for row in rows:
        try:
            candidate = SourceSignalCandidate.model_validate(json.loads(str(row["payload_json"])))
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
        histories[str(row["signal_id"])].append(
            _HistoryPoint(
                as_of_time=datetime.fromisoformat(str(row["as_of_time"])),
                status=str(row["status"]),
                score=float(row["score"] or 0),
                candidate=candidate,
            )
        )

    summaries = [_summarize_history(signal_id, points, window_days) for signal_id, points in histories.items() if points]
    summaries = [item for item in summaries if item is not None]
    spreading_count = sum(1 for item in summaries if item.spread_days is not None)
    mapped_count = sum(1 for item in summaries if item.mapped_days is not None)
    stale_count = sum(1 for item in summaries if item.spread_days is None and item.mapped_days is None)
    return SourceSignalValidationSummary(
        window_days=window_days,
        snapshot_count=snapshot_count,
        signal_count=len(summaries),
        spreading_count=spreading_count,
        mapped_count=mapped_count,
        stale_count=stale_count,
        latest_snapshot_time=latest_snapshot_time,
        by_first_status=_first_status_metrics(summaries),
        top_signals=sorted(
            summaries,
            key=lambda item: (
                item.mapped_days is None,
                item.spread_days is None,
                -(item.score or 0),
                item.first_as_of_time,
            ),
        )[:limit],
    )


class _HistoryPoint:
    def __init__(self, *, as_of_time: datetime, status: str, score: float, candidate: SourceSignalCandidate) -> None:
        self.as_of_time = as_of_time
        self.status = status
        self.score = score
        self.candidate = candidate


def _summarize_history(signal_id: str, points: list[_HistoryPoint], window_days: int) -> SourceSignalValidationRow | None:
    points.sort(key=lambda item: item.as_of_time)
    first = points[0]
    deadline = first.as_of_time + timedelta(days=window_days)
    in_window = [item for item in points if item.as_of_time <= deadline]
    latest = in_window[-1] if in_window else first
    spread_point = next((item for item in in_window if _is_spreading(item)), None)
    mapped_point = next((item for item in in_window if _is_mapped(item)), None)
    candidate = latest.candidate
    title = "".join(part for part in (candidate.modifier_span, candidate.anchor_span) if part) or candidate.novel_span or signal_id
    return SourceSignalValidationRow(
        signal_id=signal_id,
        title=title,
        first_as_of_time=first.as_of_time,
        latest_as_of_time=latest.as_of_time,
        first_status=first.candidate.status,
        latest_status=latest.candidate.status,
        score=latest.score,
        spread_days=_days_between(first.as_of_time, spread_point.as_of_time) if spread_point else None,
        mapped_days=_days_between(first.as_of_time, mapped_point.as_of_time) if mapped_point else None,
        mapped_stocks=candidate.mapped_stocks[:6],
        evidence=candidate.evidence[:3],
    )


def _first_status_metrics(rows: list[SourceSignalValidationRow]) -> list[SourceSignalValidationMetric]:
    buckets: dict[str, list[SourceSignalValidationRow]] = defaultdict(list)
    for row in rows:
        buckets[row.first_status].append(row)
    metrics: list[SourceSignalValidationMetric] = []
    for status, items in buckets.items():
        converted = [item for item in items if item.spread_days is not None or item.mapped_days is not None]
        days = [item.spread_days if item.spread_days is not None else item.mapped_days for item in converted]
        day_values = [float(item) for item in days if item is not None]
        metrics.append(
            SourceSignalValidationMetric(
                label=_status_text(status),
                sample_count=len(items),
                rate=len(converted) / len(items) if items else None,
                average_days=sum(day_values) / len(day_values) if day_values else None,
            )
        )
    return sorted(metrics, key=lambda item: (-(item.rate or 0), -item.sample_count, item.label))


def _is_spreading(point: _HistoryPoint) -> bool:
    candidate = point.candidate
    return point.status in {"spreading_watch", "mapped"} or candidate.followup_senders > 0 or candidate.asof_senders >= 2


def _is_mapped(point: _HistoryPoint) -> bool:
    return point.status == "mapped" or bool(point.candidate.mapped_stocks)


def _days_between(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds() / 86_400, 1)


def _count_snapshots(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(DISTINCT as_of_time) AS count FROM source_signal_snapshots").fetchone()
    return int(row["count"] or 0) if row else 0


def _latest_snapshot_time(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute("SELECT MAX(as_of_time) AS value FROM source_signal_snapshots").fetchone()
    value = row["value"] if row else None
    return datetime.fromisoformat(str(value)) if value else None


def _status_text(status: str) -> str:
    return {
        "source_seed": "源头初现",
        "spreading_watch": "扩散观察",
        "mapped": "个股绑定",
        "old_theme": "旧主题",
    }.get(status, status)
