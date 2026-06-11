from __future__ import annotations

from datetime import datetime

from radar.core.usecases.stock_evidence_chain.recognition import (
    StockEvidenceRecognitionContext,
    StockEvidenceThemeContext,
)
from radar.core.usecases.stock_evidence_chain.review import StockEvidenceReviewContext
from radar.core.usecases.stock_evidence_chain.sorting import stock_evidence_item_sort_key
from radar.core.usecases.stock_evidence_chain.view_models import StockEvidenceChainItem


def test_sorting_promotes_confirmed_mainline_over_early_noise():
    confirmed = _item(
        "300001.SZ",
        stage="pricing",
        rank=20,
        review_state="mainline_confirmed",
        recognition_state="confirmed",
        theme_quality=0.88,
    )
    noisy_seed = _item(
        "300002.SZ",
        stage="seed",
        rank=1,
        review_state="evidence_gap",
        recognition_state="unknown",
        theme_quality=0.0,
    )

    assert sorted([noisy_seed, confirmed], key=stock_evidence_item_sort_key) == [confirmed, noisy_seed]


def test_sorting_keeps_market_rejected_and_llm_errors_behind_reviewable_items():
    market_rejected = _item("300003.SZ", review_state="narrative_rejected", recognition_state="rejected")
    llm_error = _item("300004.SZ", review_state="llm_error", recognition_state="unknown")
    needs_market = _item("300005.SZ", review_state="needs_market_validation", recognition_state="unknown")

    assert sorted([llm_error, market_rejected, needs_market], key=stock_evidence_item_sort_key) == [
        needs_market,
        market_rejected,
        llm_error,
    ]


def _item(
    ts_code: str,
    *,
    stage: str = "formed",
    rank: int = 3,
    review_state: str,
    recognition_state: str,
    theme_quality: float = 0.72,
) -> StockEvidenceChainItem:
    theme = _theme(theme_quality) if theme_quality else None
    return StockEvidenceChainItem(
        ts_code=ts_code,
        stock_name=f"测试{ts_code[:3]}",
        stage=stage,
        stage_label={"seed": "种子期", "formed": "论证期", "pricing": "定价期"}.get(stage, stage),
        confidence=0.82,
        rank=rank,
        summary="测试判断",
        trigger_count=10,
        unique_trigger_count=7,
        sender_count=4,
        conversation_count=4,
        evidence_count=5,
        family_counts={"catalyst": 2, "research": 1},
        themes=[theme] if theme else [],
        primary_theme=theme,
        recognition=StockEvidenceRecognitionContext(state=recognition_state, state_label=recognition_state),
        review=StockEvidenceReviewContext(state=review_state, label=review_state),
        updated_at=datetime(2026, 6, 8, 15, 0),
    )


def _theme(score: float) -> StockEvidenceThemeContext:
    return StockEvidenceThemeContext(
        theme_id="theme:auto:semi",
        theme_name="半导体",
        theme_type="theme",
        role="core",
        confidence=0.86,
        source_count=3,
        quality_score=score,
        quality_label="主线候选",
    )
