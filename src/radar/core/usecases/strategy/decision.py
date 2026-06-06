from __future__ import annotations

from typing import TypeVar

from radar.core.usecases.strategy.models import StrategyRelatedStock, StrategyStockCandidate

StockWithDecision = TypeVar("StockWithDecision", StrategyRelatedStock, StrategyStockCandidate)

_ACTIONABLE_STATES = {"初现", "发酵中"}
_ACTIONABLE_POSITIONS = {"趋势健康", "可观察"}
_WEAK_POSITIONS = {"回撤偏大", "短线偏弱", "首现后走弱"}
_REALIZED_RETURN_THRESHOLD = 0.25


def annotate_related_stock_decisions(
    related_by_anchor: dict[tuple[str, str], list[StrategyRelatedStock]],
) -> dict[tuple[str, str], list[StrategyRelatedStock]]:
    return {key: _sort_stocks([_annotate_stock(stock) for stock in stocks]) for key, stocks in related_by_anchor.items()}


def annotate_stock_candidate_decisions(stocks: list[StrategyStockCandidate]) -> list[StrategyStockCandidate]:
    return _sort_stocks([_annotate_stock(stock) for stock in stocks])


def select_decision_stock_pool(stocks: list[StrategyStockCandidate], *, limit: int) -> list[StrategyStockCandidate]:
    if limit <= 0:
        return []
    sorted_stocks = _sort_stocks(stocks)
    quotas = {
        "今日可关注": max(1, round(limit * 0.35)),
        "观察等待": max(1, round(limit * 0.4)),
        "已兑现复盘": max(1, limit - round(limit * 0.35) - round(limit * 0.4)),
    }
    selected: list[StrategyStockCandidate] = []
    selected_codes: set[str] = set()
    for bucket, quota in quotas.items():
        for stock in [item for item in sorted_stocks if item.decision_bucket == bucket][:quota]:
            selected.append(stock)
            selected_codes.add(stock.ts_code)
    if len(selected) < limit:
        for stock in sorted_stocks:
            if stock.ts_code in selected_codes:
                continue
            selected.append(stock)
            selected_codes.add(stock.ts_code)
            if len(selected) >= limit:
                break
    return _sort_stocks(selected[:limit])


def _annotate_stock(stock: StockWithDecision) -> StockWithDecision:
    bucket, reason = _decision(stock)
    return stock.model_copy(update={"decision_bucket": bucket, "decision_reason": reason})


def _decision(stock: StockWithDecision) -> tuple[str, str]:
    if _is_realized(stock):
        return "已兑现复盘", "首现后涨幅已大，适合复盘来源和逻辑，不适合追高。"

    if stock.lifecycle_state == "缺少价格" or stock.price_position == "缺少价格":
        return "观察等待", "缺少价格位置，先补行情再判断。"

    credibility = stock.event_credibility
    credibility_level = credibility.level if credibility else "待验证"
    matured_count = credibility.source_matured_event_count if credibility else 0
    source_is_credible = credibility_level == "高可信" or (
        credibility_level == "中可信" and matured_count >= 5
    )

    if stock.realtime_score >= 75 and credibility_level in {"高可信", "中可信"}:
        source_is_credible = True
    if (
        stock.realtime_score >= 70
        and credibility_level == "中可信"
        and credibility is not None
        and credibility.logic_hit_count >= 4
    ):
        source_is_credible = True

    if (
        stock.lifecycle_state in _ACTIONABLE_STATES
        and stock.price_position in _ACTIONABLE_POSITIONS
        and stock.realtime_score >= 68
        and source_is_credible
    ):
        return "今日可关注", "信号仍在发酵，价格位置未过热，来源和事件质量达到关注线。"

    if credibility_level == "低可信" or stock.realtime_score < 45:
        return "观察等待", "实时分或来源可信度不足，先观察后续扩散和价格确认。"

    if stock.lifecycle_state == "回调再看" or stock.price_position in _WEAK_POSITIONS:
        return "观察等待", "首现后走势转弱或回撤偏大，需要等企稳再看。"

    if stock.price_position == "震荡观察":
        return "观察等待", "逻辑仍可跟踪，但价格处于震荡位置，等待方向确认。"

    return "观察等待", "信号质量未达到今日关注线，继续跟踪来源、扩散和 K 线位置。"


def _is_realized(stock: StockWithDecision) -> bool:
    if stock.lifecycle_state == "已兑现":
        return True
    return (
        stock.price_return_since_first_seen is not None
        and stock.price_return_since_first_seen >= _REALIZED_RETURN_THRESHOLD
    )


def _sort_stocks(stocks: list[StockWithDecision]) -> list[StockWithDecision]:
    return sorted(
        stocks,
        key=lambda stock: (
            _bucket_rank(stock.decision_bucket),
            stock.realtime_score,
            stock.average_excess_return_t5 or 0,
            stock.source_count,
            stock.event_count,
        ),
        reverse=True,
    )


def _bucket_rank(bucket: str) -> int:
    if bucket == "今日可关注":
        return 3
    if bucket == "观察等待":
        return 2
    return 1
