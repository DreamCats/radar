from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.store import connect, init_db
from radar.core.usecases.strategy.lifecycle import annotate_related_stock_lifecycle, annotate_stock_candidate_lifecycle
from radar.core.usecases.strategy.details import (
    backtest_metrics_for_anchors,
    latest_theme_briefs,
    match_themes,
    related_stocks_for_anchors,
    source_quality,
    stock_candidates,
    term_hits_for_anchor,
    top_sources_for_anchor,
)
from radar.core.usecases.strategy.models import (
    StrategyBacktestMetric,
    StrategyDashboard,
    StrategyOpportunity,
    StrategyRelatedStock,
    StrategyThemeBrief,
)
from radar.core.usecases.strategy.scoring import score_opportunity

CATALYST_TERMS = (
    "涨价",
    "订单",
    "中标",
    "放量",
    "量产",
    "业绩",
    "预增",
    "新品",
    "出货",
    "扩产",
    "供不应求",
    "提价",
    "催化",
    "招标",
    "英伟达",
    "算力",
    "服务器",
)
RISK_TERMS = (
    "不及预期",
    "砍单",
    "降价",
    "库存",
    "下修",
    "亏损",
    "制裁",
    "延期",
    "退坡",
    "稼动率",
    "减产",
    "跌价",
    "反倾销",
    "监管",
)
HIGH_VALUE_CATEGORIES = ("research", "recommendation", "industry")


@dataclass(frozen=True)
class _AnchorStats:
    name: str
    anchor_type: str
    recent_message_count: int
    previous_message_count: int
    sender_count: int
    group_count: int
    high_value_count: int
    recommendation_count: int
    research_count: int
    industry_count: int
    catalyst_count: int
    risk_count: int
    latest_message_time: datetime


def build_strategy_dashboard(
    config: RadarConfig,
    *,
    days: int = 30,
    recent_days: int = 7,
    limit: int = 10,
) -> StrategyDashboard:
    if days < 7 or days > 180:
        raise ValueError("days 必须在 7 到 180 之间")
    if recent_days < 1 or recent_days >= days:
        raise ValueError("recent_days 必须在 1 到 days-1 之间")
    if limit < 1 or limit > 50:
        raise ValueError("limit 必须在 1 到 50 之间")

    conn = connect(config.database_path)
    market_conn = connect(config.market_database_path)
    try:
        init_db(conn)
        migrate_market_db(market_conn)
        return build_strategy_dashboard_from_conn(
            conn,
            market_conn=market_conn,
            days=days,
            recent_days=recent_days,
            limit=limit,
        )
    finally:
        conn.close()
        market_conn.close()


def build_strategy_dashboard_from_conn(
    conn: sqlite3.Connection,
    *,
    market_conn: sqlite3.Connection | None = None,
    days: int = 30,
    recent_days: int = 7,
    limit: int = 10,
) -> StrategyDashboard:
    latest = _latest_message_time(conn)
    now = datetime.now()
    if latest is None:
        return StrategyDashboard(
            start_time=now,
            end_time=now,
            recent_start_time=now,
            generated_at=now,
            opportunity_count=0,
            opportunities=[],
            source_quality=[],
            stock_candidates=[],
        )

    end_time = latest
    start_time = end_time - timedelta(days=days)
    recent_start_time = end_time - timedelta(days=recent_days)
    previous_days = max((recent_start_time - start_time).total_seconds() / 86400, 1)
    themes = latest_theme_briefs(conn)
    candidates = [
        stats
        for stats in _anchor_stats(conn, start_time=start_time, recent_start_time=recent_start_time, end_time=end_time)
        if stats.recent_message_count >= 3
    ]
    shortlist_size = min(len(candidates), max(limit * 4, 30))
    shortlisted = sorted(
        candidates,
        key=lambda stats: _pre_score(stats, previous_days=previous_days),
        reverse=True,
    )[:shortlist_size]
    related_by_anchor = related_stocks_for_anchors(
        conn,
        shortlisted,
        start_time=start_time,
        end_time=end_time,
        limit_per_anchor=5,
    )
    related_by_anchor = annotate_related_stock_lifecycle(market_conn, related_by_anchor, as_of=end_time)
    backtest_by_anchor = backtest_metrics_for_anchors(
        conn,
        shortlisted,
        start_time=start_time,
        end_time=end_time,
    )
    opportunities = [
        _opportunity_from_stats(
            conn,
            stats,
            start_time=start_time,
            recent_start_time=recent_start_time,
            end_time=end_time,
            previous_days=previous_days,
            themes=themes,
            related_stocks=related_by_anchor.get((stats.anchor_type, stats.name), []),
            opportunity_backtest=backtest_by_anchor.get((stats.anchor_type, stats.name), StrategyBacktestMetric()),
        )
        for stats in shortlisted
    ]
    opportunities.sort(key=lambda item: (item.score, item.reliability_score, item.recent_message_count), reverse=True)
    stock_pool = stock_candidates(conn, start_time=start_time, end_time=end_time, limit=12)
    stock_pool = annotate_stock_candidate_lifecycle(market_conn, stock_pool, as_of=end_time)
    return StrategyDashboard(
        start_time=start_time,
        end_time=end_time,
        recent_start_time=recent_start_time,
        generated_at=now,
        opportunity_count=len(candidates),
        opportunities=opportunities[:limit],
        source_quality=source_quality(conn, start_time=start_time, end_time=end_time, limit=10),
        stock_candidates=stock_pool,
    )


def _latest_message_time(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute("SELECT MAX(message_time) AS latest_time FROM messages").fetchone()
    if row is None or row["latest_time"] is None:
        return None
    return datetime.fromisoformat(str(row["latest_time"]))


def _anchor_stats(
    conn: sqlite3.Connection,
    *,
    start_time: datetime,
    recent_start_time: datetime,
    end_time: datetime,
) -> list[_AnchorStats]:
    catalyst_expr = _keyword_expr("cat", CATALYST_TERMS)
    risk_expr = _keyword_expr("risk", RISK_TERMS)
    category_placeholders = ", ".join(f":catg{i}" for i, _ in enumerate(HIGH_VALUE_CATEGORIES))
    params: dict[str, object] = {
        "start_time": start_time.isoformat(),
        "recent_start_time": recent_start_time.isoformat(),
        "end_time": end_time.isoformat(),
    }
    params.update({f"cat{i}": f"%{term}%" for i, term in enumerate(CATALYST_TERMS)})
    params.update({f"risk{i}": f"%{term}%" for i, term in enumerate(RISK_TERMS)})
    params.update({f"catg{i}": category for i, category in enumerate(HIGH_VALUE_CATEGORIES)})
    rows = conn.execute(
        f"""
        SELECT
            a.name,
            a.anchor_type,
            COUNT(DISTINCT CASE WHEN m.message_time >= :recent_start_time THEN m.message_id END) AS recent_count,
            COUNT(DISTINCT CASE WHEN m.message_time < :recent_start_time THEN m.message_id END) AS previous_count,
            COUNT(DISTINCT CASE WHEN m.message_time >= :recent_start_time THEN m.sender END) AS sender_count,
            COUNT(DISTINCT CASE
                WHEN m.message_time >= :recent_start_time AND m.source = '个人群'
                THEN m.group_name
            END) AS group_count,
            COUNT(DISTINCT CASE
                WHEN m.message_time >= :recent_start_time
                     AND c.category IN ({category_placeholders})
                     AND c.confidence >= 0.75
                     AND c.status != 'ignored'
                THEN m.message_id
            END) AS high_value_count,
            COUNT(DISTINCT CASE WHEN m.message_time >= :recent_start_time AND c.category = 'recommendation' THEN m.message_id END) AS recommendation_count,
            COUNT(DISTINCT CASE WHEN m.message_time >= :recent_start_time AND c.category = 'research' THEN m.message_id END) AS research_count,
            COUNT(DISTINCT CASE WHEN m.message_time >= :recent_start_time AND c.category = 'industry' THEN m.message_id END) AS industry_count,
            COUNT(DISTINCT CASE
                WHEN m.message_time >= :recent_start_time
                     AND c.category IN ({category_placeholders})
                     AND c.confidence >= 0.7
                     AND c.status != 'ignored'
                     AND ({catalyst_expr})
                THEN m.message_id
            END) AS catalyst_count,
            COUNT(DISTINCT CASE
                WHEN m.message_time >= :recent_start_time
                     AND c.category IN ({category_placeholders})
                     AND c.confidence >= 0.7
                     AND c.status != 'ignored'
                     AND ({risk_expr})
                THEN m.message_id
            END) AS risk_count,
            MAX(CASE WHEN m.message_time >= :recent_start_time THEN m.message_time END) AS latest_time
        FROM message_anchors a
        JOIN messages m ON m.message_id = a.message_id
        LEFT JOIN message_classifications c ON c.message_id = m.message_id
        WHERE m.message_time >= :start_time AND m.message_time <= :end_time
        GROUP BY a.anchor_type, a.name
        HAVING recent_count > 0
        ORDER BY recent_count DESC
        LIMIT 160
        """,
        params,
    ).fetchall()
    return [
        _AnchorStats(
            name=str(row["name"]),
            anchor_type=str(row["anchor_type"]),
            recent_message_count=int(row["recent_count"] or 0),
            previous_message_count=int(row["previous_count"] or 0),
            sender_count=int(row["sender_count"] or 0),
            group_count=int(row["group_count"] or 0),
            high_value_count=int(row["high_value_count"] or 0),
            recommendation_count=int(row["recommendation_count"] or 0),
            research_count=int(row["research_count"] or 0),
            industry_count=int(row["industry_count"] or 0),
            catalyst_count=int(row["catalyst_count"] or 0),
            risk_count=int(row["risk_count"] or 0),
            latest_message_time=datetime.fromisoformat(str(row["latest_time"])),
        )
        for row in rows
        if row["latest_time"]
    ]


def _opportunity_from_stats(
    conn: sqlite3.Connection,
    stats: _AnchorStats,
    *,
    start_time: datetime,
    recent_start_time: datetime,
    end_time: datetime,
    previous_days: float,
    themes: list[StrategyThemeBrief],
    related_stocks: list[StrategyRelatedStock],
    opportunity_backtest: StrategyBacktestMetric,
) -> StrategyOpportunity:
    top_sources = top_sources_for_anchor(
        conn,
        name=stats.name,
        anchor_type=stats.anchor_type,
        recent_start_time=recent_start_time,
        end_time=end_time,
        limit=3,
    )
    matched_themes = match_themes(stats.name, themes, limit=2)
    selected_stock_backtest = _selected_stock_backtest(related_stocks)
    t5_event_count = opportunity_backtest.matured_event_count
    win_rate_t5 = opportunity_backtest.win_rate_t5
    average_excess_return_t5 = opportunity_backtest.average_excess_return_t5
    selected_t5_event_count = selected_stock_backtest.matured_event_count
    selected_win_rate_t5 = selected_stock_backtest.win_rate_t5
    selected_average_excess_return_t5 = selected_stock_backtest.average_excess_return_t5
    scored = score_opportunity(
        recent_message_count=stats.recent_message_count,
        previous_message_count=stats.previous_message_count,
        previous_days=previous_days,
        sender_count=stats.sender_count,
        group_count=stats.group_count,
        high_value_count=stats.high_value_count,
        catalyst_count=stats.catalyst_count,
        risk_count=stats.risk_count,
        t5_event_count=t5_event_count,
        win_rate_t5=win_rate_t5,
        average_excess_return_t5=average_excess_return_t5,
    )
    previous_weekly = stats.previous_message_count * 7 / max(previous_days, 1)
    acceleration = (stats.recent_message_count + 1) / (previous_weekly + 1)
    high_value_ratio = stats.high_value_count / stats.recent_message_count if stats.recent_message_count else 0
    catalyst_terms = term_hits_for_anchor(conn, stats.name, stats.anchor_type, CATALYST_TERMS, recent_start_time, end_time)
    risk_terms = term_hits_for_anchor(conn, stats.name, stats.anchor_type, RISK_TERMS, recent_start_time, end_time)
    return StrategyOpportunity(
        key=f"{stats.anchor_type}:{stats.name}",
        name=stats.name,
        anchor_type=stats.anchor_type,
        attention_level=scored.attention_level,
        score=scored.score,
        reliability_score=scored.reliability_score,
        reason=_reason(stats, acceleration=acceleration, opportunity_backtest=opportunity_backtest),
        risk_summary=_risk_summary(stats, risk_terms, scored.risk_score, scored.crowding_penalty),
        recent_message_count=stats.recent_message_count,
        previous_message_count=stats.previous_message_count,
        acceleration=round(acceleration, 2),
        sender_count=stats.sender_count,
        group_count=stats.group_count,
        high_value_count=stats.high_value_count,
        high_value_ratio=round(high_value_ratio, 3),
        recommendation_count=stats.recommendation_count,
        research_count=stats.research_count,
        industry_count=stats.industry_count,
        catalyst_count=stats.catalyst_count,
        risk_count=stats.risk_count,
        catalyst_terms=catalyst_terms,
        risk_terms=risk_terms,
        t5_event_count=t5_event_count,
        win_rate_t5=round(win_rate_t5, 4) if win_rate_t5 is not None else None,
        average_excess_return_t5=round(average_excess_return_t5, 4) if average_excess_return_t5 is not None else None,
        opportunity_backtest=StrategyBacktestMetric(
            event_count=opportunity_backtest.event_count,
            matured_event_count=opportunity_backtest.matured_event_count,
            pending_event_count=opportunity_backtest.pending_event_count,
            win_rate_t5=round(win_rate_t5, 4) if win_rate_t5 is not None else None,
            average_excess_return_t5=round(average_excess_return_t5, 4)
            if average_excess_return_t5 is not None
            else None,
        ),
        selected_stock_backtest=StrategyBacktestMetric(
            event_count=selected_stock_backtest.event_count,
            matured_event_count=selected_t5_event_count,
            pending_event_count=selected_stock_backtest.pending_event_count,
            win_rate_t5=round(selected_win_rate_t5, 4) if selected_win_rate_t5 is not None else None,
            average_excess_return_t5=round(selected_average_excess_return_t5, 4)
            if selected_average_excess_return_t5 is not None
            else None,
        ),
        latest_message_time=stats.latest_message_time,
        related_stocks=related_stocks,
        top_sources=top_sources,
        matched_themes=matched_themes,
    )


def _selected_stock_backtest(related_stocks: list[StrategyRelatedStock]) -> StrategyBacktestMetric:
    event_count = sum(stock.event_count for stock in related_stocks)
    win_rate_t5 = _weighted_average(
        [(stock.win_rate_t5, stock.event_count) for stock in related_stocks if stock.win_rate_t5 is not None]
    )
    average_excess_return_t5 = _weighted_average(
        [
            (stock.average_excess_return_t5, stock.event_count)
            for stock in related_stocks
            if stock.average_excess_return_t5 is not None
        ]
    )
    return StrategyBacktestMetric(
        event_count=event_count,
        matured_event_count=event_count,
        pending_event_count=0,
        win_rate_t5=win_rate_t5,
        average_excess_return_t5=average_excess_return_t5,
    )


def _pre_score(stats: _AnchorStats, *, previous_days: float) -> tuple[float, int, int]:
    scored = score_opportunity(
        recent_message_count=stats.recent_message_count,
        previous_message_count=stats.previous_message_count,
        previous_days=previous_days,
        sender_count=stats.sender_count,
        group_count=stats.group_count,
        high_value_count=stats.high_value_count,
        catalyst_count=stats.catalyst_count,
        risk_count=stats.risk_count,
        t5_event_count=0,
        win_rate_t5=None,
        average_excess_return_t5=None,
    )
    return scored.score, stats.sender_count, stats.recent_message_count


def _keyword_expr(prefix: str, terms: tuple[str, ...]) -> str:
    return " OR ".join(f"m.raw_content LIKE :{prefix}{index}" for index, _ in enumerate(terms))


def _weighted_average(items: list[tuple[float | None, int]]) -> float | None:
    total_weight = sum(weight for value, weight in items if value is not None)
    if total_weight <= 0:
        return None
    return sum((value or 0) * weight for value, weight in items) / total_weight


def _reason(stats: _AnchorStats, *, acceleration: float, opportunity_backtest: StrategyBacktestMetric) -> str:
    parts = [
        f"近7天 {stats.recent_message_count} 条，较前序窗口约 {acceleration:.1f}x",
        f"{stats.sender_count} 位发送人 / {stats.group_count} 个群参与",
    ]
    if opportunity_backtest.matured_event_count:
        win_text = f"{(opportunity_backtest.win_rate_t5 or 0) * 100:.0f}%"
        parts.append(f"全量机会 T+5 成熟 {opportunity_backtest.matured_event_count} 个，胜率 {win_text}")
    elif opportunity_backtest.pending_event_count:
        parts.append(f"T+5 尚未成熟 {opportunity_backtest.pending_event_count} 个事件")
    return "；".join(parts)


def _risk_summary(stats: _AnchorStats, risk_terms: list[str], risk_score: float, crowding_penalty: float) -> str:
    if crowding_penalty >= 7:
        return "讨论已经较拥挤，适合验证分歧和兑现节奏。"
    if risk_score >= 10 and risk_terms:
        return f"风险词偏高：{'、'.join(risk_terms[:3])}。"
    if stats.risk_count:
        return f"有 {stats.risk_count} 条风险相关消息，需要和催化一起验证。"
    return "当前风险词不突出，仍需看价格位置和后续验证。"
