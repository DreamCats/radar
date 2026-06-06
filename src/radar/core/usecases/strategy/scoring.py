from __future__ import annotations

from dataclasses import dataclass

from radar.core.usecases.strategy.models import StrategyAttentionLevel


@dataclass(frozen=True)
class OpportunityScore:
    score: float
    reliability_score: float
    attention_level: StrategyAttentionLevel
    risk_score: float
    crowding_penalty: float


def score_opportunity(
    *,
    recent_message_count: int,
    previous_message_count: int,
    previous_days: float,
    sender_count: int,
    group_count: int,
    high_value_count: int,
    catalyst_count: int,
    risk_count: int,
    t5_event_count: int,
    win_rate_t5: float | None,
    average_excess_return_t5: float | None,
) -> OpportunityScore:
    """把离线产物转成可解释的机会分；这里只排序关注优先级，不给交易指令。"""

    previous_weekly = previous_message_count * 7 / max(previous_days, 1)
    acceleration = (recent_message_count + 1) / (previous_weekly + 1)
    high_value_ratio = high_value_count / recent_message_count if recent_message_count else 0
    catalyst_ratio = catalyst_count / recent_message_count if recent_message_count else 0
    risk_ratio = risk_count / recent_message_count if recent_message_count else 0

    trend_score = min(30.0, acceleration * 6 + min(recent_message_count, 80) * 0.12)
    breadth_score = min(18.0, min(sender_count, 80) * 0.12 + min(group_count, 50) * 0.16)
    quality_score = min(16.0, high_value_ratio * 16)
    catalyst_score = min(12.0, catalyst_ratio * 16 + min(catalyst_count, 50) * 0.05)
    risk_score = min(18.0, risk_ratio * 18 + min(risk_count, 60) * 0.04)

    backtest_score = 0.0
    if t5_event_count > 0:
        excess_pct = max(0.0, (average_excess_return_t5 or 0) * 100)
        backtest_score = min(14.0, excess_pct * 0.35 + (win_rate_t5 or 0) * 6 + min(t5_event_count, 10) * 0.3)

    crowding_penalty = 0.0
    if recent_message_count >= 180 and acceleration < 1.8:
        crowding_penalty = min(10.0, recent_message_count / 90)
    elif sender_count >= 120 and acceleration < 1.5:
        crowding_penalty = 4.0

    sample_penalty = 0.0
    if recent_message_count < 8:
        sample_penalty += 12.0
    if sender_count < 3:
        sample_penalty += 8.0
    if 0 < t5_event_count < 3:
        sample_penalty += 4.0

    score = _clamp(
        5
        + trend_score
        + breadth_score
        + quality_score
        + catalyst_score
        + backtest_score
        - risk_score
        - crowding_penalty
        - sample_penalty,
        0,
        100,
    )
    reliability_score = _clamp(
        high_value_ratio * 30
        + min(sender_count, 40) / 40 * 20
        + min(group_count, 20) / 20 * 15
        + min(recent_message_count, 60) / 60 * 15
        + min(t5_event_count, 8) / 8 * 20
        - risk_score * 0.6,
        0,
        100,
    )

    if recent_message_count < 8 or sender_count < 3:
        attention_level: StrategyAttentionLevel = "样本不足"
    elif crowding_penalty >= 7:
        attention_level = "过度扩散"
    elif risk_score >= 10 and risk_score > catalyst_score:
        attention_level = "风险升高"
    elif score >= 70 and reliability_score >= 55:
        attention_level = "重点关注"
    else:
        attention_level = "继续验证"

    return OpportunityScore(
        score=round(score, 1),
        reliability_score=round(reliability_score, 1),
        attention_level=attention_level,
        risk_score=round(risk_score, 1),
        crowding_penalty=round(crowding_penalty, 1),
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
