from __future__ import annotations

from datetime import datetime

from radar.core.usecases.stock_evidence_chain.lifecycle_hashes import evidence_hashes
from radar.core.usecases.stock_evidence_chain.lifecycle_package import evidence_package
from radar.core.usecases.stock_evidence_chain.recognition import (
    StockEvidenceRecognitionContext,
    StockEvidenceThemeContext,
)
from radar.core.usecases.stock_evidence_chain.review import StockEvidenceReviewContext
from radar.core.usecases.stock_evidence_chain.view_models import StockEvidenceChainItem


def test_lifecycle_package_includes_review_and_theme_quality_in_hashes():
    item = _item(review_state="mainline_confirmed", quality_label="主线候选")
    package = evidence_package(item, as_of_time=datetime(2026, 6, 8, 15, 0))

    assert package["review"]["state"] == "mainline_confirmed"
    assert package["theme_candidates"][0]["quality_label"] == "主线候选"

    review_changed = evidence_package(_item(review_state="narrative_rejected", quality_label="主线候选"), as_of_time=None)
    theme_changed = evidence_package(_item(review_state="mainline_confirmed", quality_label="待确认"), as_of_time=None)
    base_hashes = evidence_hashes(package)

    assert evidence_hashes(review_changed).recognition_hash != base_hashes.recognition_hash
    assert evidence_hashes(review_changed).theme_hash == base_hashes.theme_hash
    assert evidence_hashes(theme_changed).theme_hash != base_hashes.theme_hash


def _item(*, review_state: str, quality_label: str) -> StockEvidenceChainItem:
    theme = StockEvidenceThemeContext(
        theme_id="theme:auto:cpo",
        theme_name="CPO概念",
        theme_type="concept",
        role="core",
        confidence=0.88,
        source_count=4,
        quality_score=0.84,
        quality_label=quality_label,
        quality_reasons=["多源主题归属"],
    )
    return StockEvidenceChainItem(
        ts_code="300394.SZ",
        stock_name="天孚通信",
        stage="pricing",
        stage_label="定价期",
        confidence=0.86,
        rank=1,
        summary="主题、消息和市场认可互相支撑。",
        trigger_count=12,
        unique_trigger_count=8,
        sender_count=5,
        conversation_count=5,
        evidence_count=6,
        family_counts={"catalyst": 2, "research": 1},
        themes=[theme],
        primary_theme=theme,
        recognition=StockEvidenceRecognitionContext(state="confirmed", state_label="强确认"),
        review=StockEvidenceReviewContext(state=review_state, label=review_state),
        updated_at=datetime(2026, 6, 8, 15, 0),
    )
