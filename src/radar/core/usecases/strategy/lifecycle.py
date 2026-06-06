from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TypeVar

from radar.core.usecases.strategy.models import StrategyRelatedStock, StrategyStockCandidate, StrategyStockLifecycleState

StockWithLifecycle = TypeVar("StockWithLifecycle", StrategyRelatedStock, StrategyStockCandidate)


@dataclass(frozen=True)
class _DailyPrice:
    date_key: str
    close: float


def annotate_related_stock_lifecycle(
    market_conn: sqlite3.Connection | None,
    related_by_anchor: dict[tuple[str, str], list[StrategyRelatedStock]],
    *,
    as_of: datetime,
) -> dict[tuple[str, str], list[StrategyRelatedStock]]:
    if market_conn is None:
        return related_by_anchor

    annotated: dict[tuple[str, str], list[StrategyRelatedStock]] = {}
    for key, stocks in related_by_anchor.items():
        annotated[key] = [_annotate_stock(market_conn, stock, as_of=as_of) for stock in stocks]
    return annotated


def annotate_stock_candidate_lifecycle(
    market_conn: sqlite3.Connection | None,
    stocks: list[StrategyStockCandidate],
    *,
    as_of: datetime,
) -> list[StrategyStockCandidate]:
    if market_conn is None:
        return stocks
    return [_annotate_stock(market_conn, stock, as_of=as_of) for stock in stocks]


def _annotate_stock(conn: sqlite3.Connection, stock: StockWithLifecycle, *, as_of: datetime) -> StockWithLifecycle:
    if stock.first_seen_time is None:
        return stock.model_copy(update={"lifecycle_state": "缺少价格", "lifecycle_reason": "缺少首现时间。"})

    prices = _daily_prices(conn, stock.ts_code, start=stock.first_seen_time, end=as_of)
    if not prices:
        return stock.model_copy(
            update={
                "lifecycle_state": "缺少价格",
                "lifecycle_reason": f"{_date_text(stock.first_seen_time)} 首现，本地暂无后续K线。",
                "signal_age_days": _age_days(stock.first_seen_time, as_of),
            }
        )

    first_close = prices[0].close
    latest_close = prices[-1].close
    high_close = max(item.close for item in prices)
    since_first = _ratio(latest_close, first_close)
    recent_3d = _ratio(latest_close, prices[-4].close) if len(prices) >= 4 else None
    drawdown = _ratio(latest_close, high_close)
    age_days = _age_days(stock.first_seen_time, as_of)
    state = _lifecycle_state(
        signal_age_days=age_days,
        price_return=since_first,
        drawdown=drawdown,
        event_count=stock.event_count,
        source_count=stock.source_count,
    )
    return stock.model_copy(
        update={
            "lifecycle_state": state,
            "lifecycle_reason": _reason(stock, state, since_first, recent_3d, drawdown),
            "signal_age_days": age_days,
            "price_return_since_first_seen": round(since_first, 4),
            "recent_price_return_3d": round(recent_3d, 4) if recent_3d is not None else None,
            "drawdown_from_high_since_first_seen": round(drawdown, 4),
        }
    )


def _daily_prices(conn: sqlite3.Connection, ts_code: str, *, start: datetime, end: datetime) -> list[_DailyPrice]:
    start_key = (start - timedelta(days=3)).strftime("%Y%m%d")
    end_key = end.strftime("%Y%m%d")
    try:
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
            (ts_code, start_key, end_key),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    first_key = start.strftime("%Y%m%d")
    prices: list[_DailyPrice] = []
    for row in rows:
        if str(row["date_key"]) < first_key:
            continue
        price = _price_from_row(row)
        if price is not None:
            prices.append(price)
    return prices


def _price_from_row(row: sqlite3.Row) -> _DailyPrice | None:
    try:
        payload = json.loads(str(row["data"]))
        close = float(payload["close"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if close <= 0:
        return None
    return _DailyPrice(date_key=str(row["date_key"]), close=close)


def _lifecycle_state(
    *,
    signal_age_days: int,
    price_return: float,
    drawdown: float,
    event_count: int,
    source_count: int,
) -> StrategyStockLifecycleState:
    if price_return >= 0.2:
        return "回调再看" if drawdown <= -0.08 else "已兑现"
    if signal_age_days <= 2 and price_return < 0.08:
        return "初现"
    if source_count >= 3 or event_count >= 3 or signal_age_days <= 7:
        return "发酵中"
    return "发酵中"


def _reason(
    stock: StrategyRelatedStock,
    state: StrategyStockLifecycleState,
    price_return: float,
    recent_3d: float | None,
    drawdown: float,
) -> str:
    pieces = [
        f"{_date_text(stock.first_seen_time)} 首现",
        f"{stock.source_count} 来源/{stock.event_count} 事件",
        f"首现后 {_format_signed_percent(price_return)}",
    ]
    if recent_3d is not None:
        pieces.append(f"近3交易日 {_format_signed_percent(recent_3d)}")
    if state == "回调再看":
        pieces.append(f"高点回撤 {_format_signed_percent(drawdown)}")
    return "，".join(pieces)


def _ratio(current: float, base: float) -> float:
    if base <= 0:
        return 0
    return current / base - 1


def _age_days(first_seen: datetime, as_of: datetime) -> int:
    return max((as_of.date() - first_seen.date()).days, 0)


def _date_text(value: datetime | None) -> str:
    return value.strftime("%m-%d") if value else "-"


def _format_signed_percent(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f}%"
