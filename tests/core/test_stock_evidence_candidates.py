from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from radar.core.usecases.stock_evidence_chain.models import Stock, StockCandidate
from radar.core.usecases.stock_evidence_chain.storage import load_candidates, load_evidence_pack


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


def test_load_evidence_pack_keeps_current_window_when_history_is_long():
    conn = _conn()
    evidence_start = datetime(2026, 5, 1, 15, 0)
    window_start = datetime(2026, 6, 13, 15, 0)
    as_of = datetime(2026, 6, 14, 11, 35)
    candidate = StockCandidate(stock=Stock(ts_code="688041.SH", symbol="688041", name="海光信息"))
    for index in range(85):
        _insert_message_mention(
            conn,
            ts_code="688041.SH",
            stock_name="海光信息",
            message_id=f"history-{index}",
            message_time=datetime(2026, 5, 5, 16, index % 60),
            fingerprint=f"history-{index}",
            raw_content=f"历史证据 {index}",
            score=3,
            families=["catalyst"],
        )
    _insert_message_mention(
        conn,
        ts_code="688041.SH",
        stock_name="海光信息",
        message_id="current-1",
        message_time=datetime(2026, 6, 13, 17, 38),
        fingerprint="current-1",
        raw_content="本次窗口新增触发",
        score=3,
        families=["catalyst"],
    )

    pack = load_evidence_pack(
        conn,
        candidate=candidate,
        window_start=window_start,
        evidence_start=evidence_start,
        as_of=as_of,
        max_items=80,
    )

    assert len(pack.evidence) == 80
    assert "current-1" in {item.message.message_id for item in pack.evidence}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE messages (
            message_id TEXT PRIMARY KEY,
            source TEXT,
            sender TEXT,
            message_time TEXT,
            raw_content TEXT,
            group_name TEXT
        )
        """
    )
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


def _insert_message_mention(
    conn: sqlite3.Connection,
    *,
    ts_code: str,
    stock_name: str,
    message_id: str,
    message_time: datetime,
    fingerprint: str,
    raw_content: str,
    score: int,
    families: list[str],
) -> None:
    symbol = ts_code.split(".", 1)[0]
    conn.execute(
        """
        INSERT INTO messages (
            message_id, source, sender, message_time, raw_content, group_name
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (message_id, "group_message", "sender", message_time.isoformat(), raw_content, "group"),
    )
    conn.execute(
        """
        INSERT INTO stock_message_mentions (
            message_id, ts_code, stock_name, symbol, message_time, source, sender,
            group_name, category, fingerprint, evidence_score, evidence_families_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            ts_code,
            stock_name,
            symbol,
            message_time.isoformat(),
            "group_message",
            "sender",
            "group",
            "research",
            fingerprint,
            score,
            json.dumps(families, ensure_ascii=False),
        ),
    )
    conn.commit()
