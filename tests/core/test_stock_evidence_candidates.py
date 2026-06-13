from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from radar.core.usecases.stock_evidence_chain.storage import load_candidates


def test_load_candidates_adds_watch_fallback_when_strong_pool_is_small():
    conn = _conn()
    start = datetime(2026, 6, 12, 15, 0)
    end = datetime(2026, 6, 13, 23, 55)
    _insert_mentions(conn, start, "300001.SZ", "强候选", count=3, senders=2, conversations=2, score=3, families=["catalyst"])
    _insert_mentions(conn, start, "300002.SZ", "观察候选", count=2, senders=2, conversations=2, score=4, families=["research", "push"])
    _insert_mentions(conn, start, "300003.SZ", "弱候选", count=2, senders=1, conversations=1, score=4, families=["research", "push"])

    candidates = load_candidates(conn, window_start=start, as_of=end)

    by_code = {item.stock.ts_code: item for item in candidates}
    assert list(by_code) == ["300001.SZ", "300002.SZ"]
    assert by_code["300001.SZ"].channels == {"early_strong"}
    assert by_code["300002.SZ"].channels == {"watch"}


def test_load_candidates_skips_watch_fallback_when_strong_pool_is_full():
    conn = _conn()
    start = datetime(2026, 6, 12, 15, 0)
    end = datetime(2026, 6, 13, 23, 55)
    for index in range(50):
        _insert_mentions(conn, start, f"30{index:04d}.SZ", f"强候选{index}", count=3, senders=2, conversations=2, score=3, families=["catalyst"])
    _insert_mentions(conn, start, "300999.SZ", "观察候选", count=2, senders=2, conversations=2, score=4, families=["research", "push"])

    candidates = load_candidates(conn, window_start=start, as_of=end)

    assert len(candidates) == 50
    assert "300999.SZ" not in {item.stock.ts_code for item in candidates}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE stock_message_mentions (
            message_id TEXT,
            ts_code TEXT,
            stock_name TEXT,
            symbol TEXT,
            message_time TEXT,
            source TEXT,
            sender TEXT,
            group_name TEXT,
            category TEXT,
            fingerprint TEXT,
            evidence_score INTEGER,
            evidence_families_json TEXT
        )
        """
    )
    return conn


def _insert_mentions(
    conn: sqlite3.Connection,
    start: datetime,
    ts_code: str,
    stock_name: str,
    *,
    count: int,
    senders: int,
    conversations: int,
    score: int,
    families: list[str],
) -> None:
    symbol = ts_code.split(".", 1)[0]
    for index in range(count):
        conn.execute(
            """
            INSERT INTO stock_message_mentions (
                message_id, ts_code, stock_name, symbol, message_time, source, sender,
                group_name, category, fingerprint, evidence_score, evidence_families_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{ts_code}-{index}",
                ts_code,
                stock_name,
                symbol,
                start.isoformat(),
                "group_message",
                f"sender-{index % senders}",
                f"group-{index % conversations}",
                "research",
                f"{ts_code}-fingerprint-{index}",
                score,
                json.dumps(families, ensure_ascii=False),
            ),
        )
    conn.commit()
