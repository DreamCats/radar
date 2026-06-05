from __future__ import annotations

import sqlite3
from datetime import datetime

from radar.core.usecases.aggregation.models import RefineAggregateTopicsResult


def load_refine_result(conn: sqlite3.Connection, input_hash: str) -> RefineAggregateTopicsResult | None:
    row = conn.execute(
        """
        SELECT result_json
        FROM aggregate_refine_results
        WHERE input_hash = ?
        """,
        (input_hash,),
    ).fetchone()
    if row is None:
        return None
    return RefineAggregateTopicsResult.model_validate_json(row["result_json"])


def list_refine_results(conn: sqlite3.Connection, *, limit: int = 10) -> list[RefineAggregateTopicsResult]:
    if limit < 1 or limit > 50:
        raise ValueError("limit 必须在 1 到 50 之间")
    rows = conn.execute(
        """
        SELECT result_json
        FROM aggregate_refine_results
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [RefineAggregateTopicsResult.model_validate_json(row["result_json"]) for row in rows]


def store_refine_result(conn: sqlite3.Connection, result: RefineAggregateTopicsResult) -> None:
    now = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO aggregate_refine_results (
            input_hash, run_id, trade_date, start_time, end_time, extractor_version,
            prompt_version, candidate_count, theme_count, result_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(input_hash) DO UPDATE SET
            run_id = excluded.run_id,
            candidate_count = excluded.candidate_count,
            theme_count = excluded.theme_count,
            result_json = excluded.result_json,
            updated_at = excluded.updated_at
        """,
        (
            result.input_hash,
            result.run_id,
            result.trade_date,
            result.local_result.start_time.isoformat(),
            result.local_result.end_time.isoformat(),
            result.extractor_version,
            result.prompt_version,
            result.candidate_count,
            result.theme_count,
            result.model_dump_json(),
            now,
            now,
        ),
    )
    conn.commit()
