from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db, migrate_message_db
from radar.core.store import connect
from radar.core.tushare import client as tushare_client
from radar.core.tushare import history
from radar.core.tushare.exceptions import TushareError


def ensure_lead_signal_daily_quotes(config: RadarConfig, *, as_of_date: str | None = None) -> None:
    spec = history.spec_for("daily")
    if spec is None:
        return

    with connect(config.database_path) as conn:
        migrate_message_db(conn)
        selected_date = _resolve_selected_date(conn, as_of_date)
        if selected_date is None:
            return
        selected_start, selected_end = _date_bounds(selected_date)
        ts_codes = _event_ts_codes(conn, start_time=selected_start, end_time=selected_end)

    if not ts_codes:
        return

    trade_date = selected_date.replace("-", "")
    if trade_date > history.cacheable_end_key(spec.date_kind):
        return
    if not _missing_daily_codes(config, trade_date=trade_date, ts_codes=ts_codes):
        return

    try:
        rows = tushare_client.call(config, "daily", {"trade_date": trade_date}, use_cache=True)
    except TushareError:
        return
    if rows:
        history.put_rows(config.market_database_path, spec, rows)


def _resolve_selected_date(conn: sqlite3.Connection, value: str | None) -> str | None:
    if value:
        return _display_date(value)
    row = conn.execute(
        """
        SELECT event_date
        FROM recommendation_events
        ORDER BY event_date DESC
        LIMIT 1
        """
    ).fetchone()
    return _display_date(str(row["event_date"])) if row is not None and row["event_date"] else None


def _event_ts_codes(conn: sqlite3.Connection, *, start_time: datetime, end_time: datetime) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT ts_code
        FROM recommendation_events
        WHERE action = 'bullish'
          AND message_time >= ?
          AND message_time < ?
        """,
        (start_time.isoformat(), end_time.isoformat()),
    ).fetchall()
    return {str(row["ts_code"]) for row in rows if row["ts_code"]}


def _missing_daily_codes(config: RadarConfig, *, trade_date: str, ts_codes: set[str]) -> set[str]:
    if not ts_codes:
        return set()
    placeholders = ",".join("?" for _ in ts_codes)
    with connect(config.market_database_path) as conn:
        migrate_market_db(conn)
        rows = conn.execute(
            f"""
            SELECT ts_code
            FROM tushare_history
            WHERE api_name = 'daily'
              AND date_key = ?
              AND ts_code IN ({placeholders})
            """,
            [trade_date, *sorted(ts_codes)],
        ).fetchall()
    existing = {str(row["ts_code"]) for row in rows if row["ts_code"]}
    return ts_codes - existing


def _date_bounds(value: str) -> tuple[datetime, datetime]:
    parsed = date.fromisoformat(_display_date(value))
    start = datetime.combine(parsed, time.min)
    return start, start + timedelta(days=1)


def _display_date(value: str) -> str:
    compact = value.strip()
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
    return date.fromisoformat(compact).isoformat()
