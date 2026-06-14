from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from radar.core.config import RadarConfig
from radar.core.tushare import client as tushare_client
from radar.core.tushare.exceptions import TushareError
from radar.core.usecases.stock_evidence_chain.models import MarketEvidence, MarketPoint, StockMention


@dataclass(frozen=True)
class _DailyRow:
    trade_date: str
    close: float
    pct_chg: float | None
    amount: float | None


def load_market_evidence(
    config: RadarConfig,
    conn: sqlite3.Connection,
    *,
    ts_code: str,
    evidence: list[StockMention],
    window_start: datetime | None = None,
    evidence_start: datetime,
    as_of: datetime,
) -> MarketEvidence | None:
    start = evidence_start - timedelta(days=10)
    _refresh_daily(config, ts_code=ts_code, start=start, end=as_of)
    rows = _daily_rows(conn, ts_code=ts_code, start=start, end=as_of)
    if not rows:
        return None
    indexed = {row.trade_date: row for row in rows}
    evidence_dates = _selected_evidence_dates(evidence, window_start=window_start)
    selected_keys = _selected_trade_dates(rows, evidence_dates, as_of.strftime("%Y%m%d"))
    latest_key = selected_keys[-1] if selected_keys else None
    points = [
        _point(indexed[key], tag="latest" if key == latest_key else "evidence_day", previous=rows[: rows.index(indexed[key])])
        for key in selected_keys
    ]
    return MarketEvidence(points=points, summary=_summary(rows, selected_keys))


def _refresh_daily(config: RadarConfig, *, ts_code: str, start: datetime, end: datetime) -> None:
    try:
        tushare_client.call(
            config,
            "daily",
            {
                "ts_code": ts_code,
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
            use_cache=True,
        )
    except TushareError:
        # 市场证据用于增强阶段判断；源头临时不可用时继续使用已有本地缓存。
        return


def _daily_rows(
    conn: sqlite3.Connection,
    *,
    ts_code: str,
    start: datetime,
    end: datetime,
) -> list[_DailyRow]:
    rows = conn.execute(
        """
        SELECT date_key, data
        FROM tushare_history
        WHERE api_name = 'daily'
          AND ts_code = ?
          AND date_key >= ?
          AND date_key <= ?
        ORDER BY date_key
        """,
        (ts_code, start.strftime("%Y%m%d"), end.strftime("%Y%m%d")),
    ).fetchall()
    parsed: list[_DailyRow] = []
    for row in rows:
        item = _row(row)
        if item is not None:
            parsed.append(item)
    return parsed


def _row(row: sqlite3.Row) -> _DailyRow | None:
    try:
        payload = json.loads(str(row["data"]))
        close = float(payload["close"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if close <= 0:
        return None
    return _DailyRow(
        trade_date=str(row["date_key"]),
        close=close,
        pct_chg=_float(payload.get("pct_chg")),
        amount=_float(payload.get("amount")),
    )


def _selected_trade_dates(rows: list[_DailyRow], evidence_dates: list[str], as_of_key: str) -> list[str]:
    trade_dates = [row.trade_date for row in rows]
    selected: list[str] = []
    for date_key in evidence_dates:
        nearest = _nearest_on_or_before(trade_dates, date_key)
        if nearest and nearest not in selected:
            selected.append(nearest)
    latest = _nearest_on_or_before(trade_dates, as_of_key)
    if latest and latest not in selected:
        selected.append(latest)
    return selected[-12:]


def _selected_evidence_dates(evidence: list[StockMention], *, window_start: datetime | None) -> list[str]:
    all_dates: list[str] = []
    selected: list[str] = []
    for item in evidence:
        date_key = item.message.message_time.strftime("%Y%m%d")
        all_dates.append(date_key)
        if window_start is not None and item.message.message_time >= window_start:
            selected.append(date_key)
            continue
        if item.evidence_score > 0 or item.evidence_families:
            selected.append(date_key)
    return sorted(set(selected or all_dates))


def _nearest_on_or_before(trade_dates: list[str], date_key: str) -> str | None:
    candidates = [item for item in trade_dates if item <= date_key]
    return candidates[-1] if candidates else None


def _point(row: _DailyRow, *, tag: str, previous: list[_DailyRow]) -> MarketPoint:
    previous_amounts = [item.amount for item in previous[-5:] if item.amount and item.amount > 0]
    avg_amount = sum(previous_amounts) / len(previous_amounts) if previous_amounts else None
    ratio = row.amount / avg_amount if row.amount and avg_amount else None
    return MarketPoint(
        trade_date=row.trade_date,
        close=round(row.close, 4),
        pct_chg=round(row.pct_chg, 4) if row.pct_chg is not None else None,
        amount=round(row.amount, 4) if row.amount is not None else None,
        amount_ratio_5d=round(ratio, 4) if ratio is not None else None,
        tag=tag,
    )


def _summary(rows: list[_DailyRow], selected_keys: list[str]) -> dict[str, Any]:
    selected = [row for row in rows if row.trade_date in selected_keys]
    if not selected:
        return {}
    first = selected[0]
    latest = selected[-1]
    high = max(selected, key=lambda item: item.close)
    return_rate = (latest.close - first.close) / first.close if first.close else None
    drawdown = (latest.close - high.close) / high.close if high.close else None
    return {
        "first_trade_date": first.trade_date,
        "first_close": round(first.close, 4),
        "latest_trade_date": latest.trade_date,
        "latest_close": round(latest.close, 4),
        "return_since_first_point": round(return_rate, 4) if return_rate is not None else None,
        "high_trade_date": high.trade_date,
        "high_close": round(high.close, 4),
        "drawdown_from_selected_high": round(drawdown, 4) if drawdown is not None else None,
    }


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
