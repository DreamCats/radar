from __future__ import annotations

from radar.core.usecases.stock_evidence_chain.recognition import (
    StockEvidenceRecognitionContext,
    StockEvidenceThemeContext,
)
from radar.core.usecases.stock_evidence_chain.review import build_review_context


def test_review_marks_llm_error_before_normal_labels():
    review = build_review_context(
        stage="formed",
        stage_label="论证期",
        confidence=None,
        summary="The request was rejected because it was considered high risk",
        unique_trigger_count=4,
        market_summary={"return_since_first_point": 0.48},
        market_points=[{"pct_chg": 2.7, "amount_ratio_5d": 1.2}],
        primary_theme=None,
        recognition=StockEvidenceRecognitionContext(state="unknown", state_label="证据不足"),
    )

    assert review.state == "llm_error"
    assert review.action_label == "重跑"


def test_review_distinguishes_market_first_and_one_day_pulse():
    market_first = build_review_context(
        stage="formed",
        stage_label="论证期",
        confidence=0.75,
        summary="逻辑链条完整但扩散不足。",
        unique_trigger_count=3,
        market_summary={"return_since_first_point": 0.28},
        market_points=[{"pct_chg": 10.0, "amount_ratio_5d": 1.3}],
        primary_theme=_theme(),
        recognition=StockEvidenceRecognitionContext(state="confirmed", state_label="强确认"),
    )
    pulse = build_review_context(
        stage="pricing",
        stage_label="定价期",
        confidence=0.82,
        summary="政策催化当日放量大涨。",
        unique_trigger_count=9,
        market_summary={"return_since_first_point": -0.08},
        market_points=[{"pct_chg": 8.8, "amount_ratio_5d": 1.8}],
        primary_theme=None,
        recognition=StockEvidenceRecognitionContext(state="rejected", state_label="市场不认"),
    )

    assert market_first.label == "市场先行消息滞后"
    assert pulse.label == "单日脉冲待验证"


def test_review_marks_volume_start_validation():
    review = build_review_context(
        stage="formed",
        stage_label="论证期",
        confidence=0.74,
        summary="逻辑开始成型，当天放量上涨。",
        unique_trigger_count=8,
        market_summary={"return_since_first_point": 0.0078, "drawdown_from_selected_high": 0.0},
        market_points=[{"pct_chg": 3.76, "amount_ratio_5d": 2.0}],
        primary_theme=_theme(),
        recognition=StockEvidenceRecognitionContext(state="just_started", state_label="刚启动"),
    )

    assert review.state == "volume_start_validation"
    assert review.label == "放量初动待验证"
    assert review.action_label == "等承接"


def test_review_flags_price_rejected_diffusion_and_mainline_confirmed():
    rejected = build_review_context(
        stage="spreading",
        stage_label="扩散期",
        confidence=0.82,
        summary="多机构密集推荐。",
        unique_trigger_count=14,
        market_summary={"return_since_first_point": -0.4, "drawdown_from_selected_high": -0.45},
        market_points=[{"pct_chg": -7.2, "amount_ratio_5d": 0.7}],
        primary_theme=_theme(),
        recognition=StockEvidenceRecognitionContext(state="rejected", state_label="市场不认"),
    )
    confirmed = build_review_context(
        stage="pricing",
        stage_label="定价期",
        confidence=0.85,
        summary="半导体设备逻辑明确且量价确认。",
        unique_trigger_count=11,
        market_summary={"return_since_first_point": 0.28, "drawdown_from_selected_high": -0.05},
        market_points=[{"pct_chg": 0.2, "amount_ratio_5d": 1.7}],
        primary_theme=_theme(),
        recognition=StockEvidenceRecognitionContext(state="confirmed", state_label="强确认"),
    )

    assert rejected.label == "消息扩散被价格否决"
    assert confirmed.label == "主线明确且市场确认"


def _theme() -> StockEvidenceThemeContext:
    return StockEvidenceThemeContext(
        theme_id="theme:auto:semi",
        theme_name="半导体",
        theme_type="theme",
        role="elastic",
        confidence=0.82,
        source_count=2,
    )
