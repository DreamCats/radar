from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

from radar.core.usecases.strategy.models import (
    StrategyEventCredibility,
    StrategyEventCredibilityLevel,
    StrategyRelatedStock,
    StrategyStockCandidate,
)

StockWithSignal = TypeVar("StockWithSignal", StrategyRelatedStock, StrategyStockCandidate)

LOGIC_TERMS = (
    "涨价",
    "订单",
    "中标",
    "放量",
    "量产",
    "出货",
    "扩产",
    "供不应求",
    "客户",
    "突破",
    "缺口",
    "稼动率",
    "业绩",
    "利润",
    "预期差",
)
HYPE_TERMS = ("翻倍", "空间巨大", "目标市值", "大力推", "强烈推荐", "不要错过", "金股", "珍惜")


@dataclass(frozen=True)
class _FirstEvent:
    event_time: datetime
    source_name: str
    group_name: str | None
    raw_content: str
    message_stock_count: int


@dataclass(frozen=True)
class _SourceStats:
    matured_event_count: int
    win_rate_t5: float | None
    average_excess_return_t5: float | None


def annotate_related_stock_credibility(
    conn: sqlite3.Connection,
    related_by_anchor: dict[tuple[str, str], list[StrategyRelatedStock]],
    *,
    start_time: datetime,
    end_time: datetime,
) -> dict[tuple[str, str], list[StrategyRelatedStock]]:
    source_cache: dict[str, _SourceStats] = {}
    annotated: dict[tuple[str, str], list[StrategyRelatedStock]] = {}
    for (anchor_type, name), stocks in related_by_anchor.items():
        next_stocks: list[StrategyRelatedStock] = []
        for stock in stocks:
            event = _first_related_event(
                conn,
                anchor_type=anchor_type,
                anchor_name=name,
                stock_name=stock.stock_name,
                ts_code=stock.ts_code,
                start_time=start_time,
                end_time=end_time,
            )
            next_stocks.append(_annotate_stock(conn, stock, event, source_cache))
        annotated[(anchor_type, name)] = next_stocks
    return annotated


def annotate_stock_candidate_credibility(
    conn: sqlite3.Connection,
    stocks: list[StrategyStockCandidate],
    *,
    start_time: datetime,
    end_time: datetime,
) -> list[StrategyStockCandidate]:
    source_cache: dict[str, _SourceStats] = {}
    return [
        _annotate_stock(
            conn,
            stock,
            _first_stock_event(conn, stock_name=stock.stock_name, ts_code=stock.ts_code, start_time=start_time, end_time=end_time),
            source_cache,
        )
        for stock in stocks
    ]


def _annotate_stock(
    conn: sqlite3.Connection,
    stock: StockWithSignal,
    event: _FirstEvent | None,
    source_cache: dict[str, _SourceStats],
) -> StockWithSignal:
    if event is None:
        return stock.model_copy(
            update={
                "realtime_score": _bounded_score(20 + _price_points(stock)),
                "event_credibility": StrategyEventCredibility(
                    level="待验证",
                    reasons=["未找到首个推荐事件"],
                    risks=["缺少事件上下文"],
                ),
            }
        )

    source_stats = source_cache.get(event.source_name)
    if source_stats is None:
        source_stats = _source_stats(conn, event.source_name)
        source_cache[event.source_name] = source_stats
    logic_hits = _term_hits(event.raw_content, LOGIC_TERMS)
    hype_hits = _term_hits(event.raw_content, HYPE_TERMS)
    score, reasons, risks = _score_event(stock, event, source_stats, logic_hits=logic_hits, hype_hits=hype_hits)
    level = _level(score, source_stats)
    credibility = StrategyEventCredibility(
        score=round(score, 1),
        level=level,
        first_source_name=event.source_name,
        first_group_name=event.group_name,
        first_event_time=event.event_time,
        first_message_stock_count=event.message_stock_count,
        source_matured_event_count=source_stats.matured_event_count,
        source_win_rate_t5=round(source_stats.win_rate_t5, 4) if source_stats.win_rate_t5 is not None else None,
        source_average_excess_return_t5=round(source_stats.average_excess_return_t5, 4)
        if source_stats.average_excess_return_t5 is not None
        else None,
        logic_hit_count=logic_hits,
        hype_hit_count=hype_hits,
        reasons=reasons[:4],
        risks=risks[:3],
    )
    return stock.model_copy(update={"realtime_score": round(score, 1), "event_credibility": credibility})


def _score_event(
    stock: StockWithSignal,
    event: _FirstEvent,
    source_stats: _SourceStats,
    *,
    logic_hits: int,
    hype_hits: int,
) -> tuple[float, list[str], list[str]]:
    score = 25.0
    reasons: list[str] = []
    risks: list[str] = []

    score += _source_points(source_stats, reasons, risks)
    logic_points = min(logic_hits * 4, 20)
    score += logic_points
    if logic_hits >= 3:
        reasons.append(f"首条事件有 {logic_hits} 个产业逻辑词")
    elif logic_hits == 0:
        risks.append("首条事件缺少明确产业逻辑词")

    diffusion_points = min(stock.source_count * 4 + stock.event_count * 1.5, 15)
    score += diffusion_points
    if stock.source_count >= 3:
        reasons.append(f"{stock.source_count} 个来源共同提到")
    elif stock.source_count <= 1:
        risks.append("当前仍是单来源信号")

    price_points = _price_points(stock)
    score += price_points
    if stock.price_position in ("趋势健康", "可观察"):
        reasons.append(f"价格位置 {stock.price_position}")
    elif stock.price_position in ("回撤偏大", "短线偏弱", "首现后走弱"):
        risks.append(f"价格位置 {stock.price_position}")
    if stock.lifecycle_state == "已兑现":
        risks.append("已兑现，追高性价比下降")

    if event.message_stock_count > 6:
        score -= 10
        risks.append("首条消息偏篮子推荐")
    elif event.message_stock_count > 3:
        score -= 5
        risks.append("首条消息覆盖股票较多")

    if hype_hits:
        score -= min(hype_hits * 4, 12)
        risks.append("首条事件含强推荐/空间类话术")

    return _bounded_score(score), reasons, risks


def _source_points(source_stats: _SourceStats, reasons: list[str], risks: list[str]) -> float:
    if source_stats.matured_event_count < 5:
        risks.append("来源成熟样本不足")
        return 4
    win_rate = source_stats.win_rate_t5 or 0
    avg_excess = source_stats.average_excess_return_t5 or 0
    if source_stats.matured_event_count >= 20 and win_rate >= 0.6 and avg_excess >= 0.03:
        reasons.append("来源历史胜率和超额较好")
        return 25
    if source_stats.matured_event_count >= 10 and avg_excess > 0:
        reasons.append("来源历史超额为正")
        return 15
    if avg_excess < 0 or win_rate < 0.45:
        risks.append("来源历史表现一般")
        return 3
    return 10


def _price_points(stock: StockWithSignal) -> float:
    points = {
        "趋势健康": 15,
        "可观察": 10,
        "震荡观察": 5,
        "缺少价格": 0,
        "回撤偏大": -8,
        "短线偏弱": -10,
        "首现后走弱": -12,
    }.get(stock.price_position or "缺少价格", 0)
    if stock.lifecycle_state == "初现":
        points += 8
    elif stock.lifecycle_state == "已兑现":
        points -= 18
    elif stock.lifecycle_state == "回调再看":
        points -= 5
    return points


def _level(score: float, source_stats: _SourceStats) -> StrategyEventCredibilityLevel:
    if score >= 75 and source_stats.matured_event_count >= 5:
        return "高可信"
    if score >= 55:
        return "中可信"
    if score >= 38:
        return "待验证"
    return "低可信"


def _first_related_event(
    conn: sqlite3.Connection,
    *,
    anchor_type: str,
    anchor_name: str,
    stock_name: str,
    ts_code: str,
    start_time: datetime,
    end_time: datetime,
) -> _FirstEvent | None:
    row = conn.execute(
        """
        SELECT
            e.message_time,
            COALESCE(e.analyst_display_name, e.source_candidate, m.sender) AS source_name,
            m.group_name,
            m.raw_content,
            (SELECT COUNT(DISTINCT e2.event_id) FROM recommendation_events e2 WHERE e2.message_id = e.message_id)
                AS message_stock_count
        FROM recommendation_events e
        JOIN message_anchors a ON a.message_id = e.message_id
        LEFT JOIN messages m ON m.message_id = e.message_id
        WHERE a.anchor_type = ?
          AND a.name = ?
          AND e.stock_name = ?
          AND e.ts_code = ?
          AND e.message_time >= ?
          AND e.message_time <= ?
        ORDER BY e.message_time ASC
        LIMIT 1
        """,
        (anchor_type, anchor_name, stock_name, ts_code, start_time.isoformat(), end_time.isoformat()),
    ).fetchone()
    return _event_from_row(row)


def _first_stock_event(
    conn: sqlite3.Connection,
    *,
    stock_name: str,
    ts_code: str,
    start_time: datetime,
    end_time: datetime,
) -> _FirstEvent | None:
    row = conn.execute(
        """
        SELECT
            e.message_time,
            COALESCE(e.analyst_display_name, e.source_candidate, m.sender) AS source_name,
            m.group_name,
            m.raw_content,
            (SELECT COUNT(DISTINCT e2.event_id) FROM recommendation_events e2 WHERE e2.message_id = e.message_id)
                AS message_stock_count
        FROM recommendation_events e
        LEFT JOIN messages m ON m.message_id = e.message_id
        WHERE e.stock_name = ?
          AND e.ts_code = ?
          AND e.message_time >= ?
          AND e.message_time <= ?
        ORDER BY e.message_time ASC
        LIMIT 1
        """,
        (stock_name, ts_code, start_time.isoformat(), end_time.isoformat()),
    ).fetchone()
    return _event_from_row(row)


def _source_stats(conn: sqlite3.Connection, source_name: str) -> _SourceStats:
    row = conn.execute(
        """
        SELECT
            COUNT(DISTINCT CASE WHEN w.status = 'succeeded' THEN e.event_id END) AS matured_event_count,
            AVG(CASE WHEN w.status = 'succeeded' THEN w.win END) AS win_rate,
            AVG(CASE WHEN w.status = 'succeeded' THEN w.excess_return_rate END) AS average_excess_return
        FROM recommendation_events e
        LEFT JOIN messages m ON m.message_id = e.message_id
        LEFT JOIN recommendation_backtest_windows w ON w.event_id = e.event_id AND w.window_days = 5
        WHERE COALESCE(e.analyst_display_name, e.source_candidate, m.sender) = ?
        """,
        (source_name,),
    ).fetchone()
    if row is None:
        return _SourceStats(matured_event_count=0, win_rate_t5=None, average_excess_return_t5=None)
    return _SourceStats(
        matured_event_count=int(row["matured_event_count"] or 0),
        win_rate_t5=float(row["win_rate"]) if row["win_rate"] is not None else None,
        average_excess_return_t5=float(row["average_excess_return"]) if row["average_excess_return"] is not None else None,
    )


def _event_from_row(row: sqlite3.Row | None) -> _FirstEvent | None:
    if row is None or not row["message_time"]:
        return None
    return _FirstEvent(
        event_time=datetime.fromisoformat(str(row["message_time"])),
        source_name=str(row["source_name"] or ""),
        group_name=str(row["group_name"]) if row["group_name"] else None,
        raw_content=str(row["raw_content"] or ""),
        message_stock_count=int(row["message_stock_count"] or 0),
    )


def _term_hits(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def _bounded_score(value: float) -> float:
    return min(100.0, max(0.0, value))
