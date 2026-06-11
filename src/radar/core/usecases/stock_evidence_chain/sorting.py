from __future__ import annotations

from radar.core.usecases.stock_evidence_chain.view_models import StockEvidenceChainItem

STAGE_ACTION_PRIORITY = {
    "seed": 60,
    "formed": 60,
    "lead": 50,
    "spreading": 45,
    "pricing": 35,
    "crowded": 5,
}
REVIEW_PRIORITY = {
    "mainline_confirmed": 0,
    "market_first": 1,
    "volume_start_validation": 6,
    "needs_market_validation": 8,
    "theme_missing": 12,
    "one_day_pulse": 16,
    "evidence_gap": 24,
    "price_rejected_diffusion": 42,
    "narrative_rejected": 44,
    "overheated_review": 50,
    "llm_error": 60,
}
RECOGNITION_PRIORITY = {
    "confirmed": 0,
    "just_confirmed": 1,
    "just_started": 2,
    "unknown": 3,
    "pullback_after_pricing": 4,
    "rejected": 5,
    "overheated": 6,
}
FAMILY_WEIGHTS = {
    "catalyst": 5,
    "roadshow": 4,
    "research": 3,
    "push": 3,
    "price": 1,
}


def stock_evidence_item_sort_key(item: StockEvidenceChainItem) -> tuple[int, int, int, int, int, int, int, int, int, str]:
    confidence = item.confidence or 0
    return (
        REVIEW_PRIORITY.get(item.review.state, 30),
        -STAGE_ACTION_PRIORITY.get(item.stage, 30),
        -_theme_quality_score(item),
        RECOGNITION_PRIORITY.get(item.recognition.state, 9),
        -_evidence_strength(item),
        -_incremental_score(item),
        -_diffusion_score(item),
        -int(confidence * 100),
        item.rank or 999999,
        _reverse_time_key(item.updated_at.isoformat()),
    )


def _theme_quality_score(item: StockEvidenceChainItem) -> int:
    theme = item.primary_theme or (item.themes[0] if item.themes else None)
    return int((theme.quality_score if theme else 0) * 100)


def _evidence_strength(item: StockEvidenceChainItem) -> int:
    score = item.evidence_count
    for family, weight in FAMILY_WEIGHTS.items():
        score += int(item.family_counts.get(family) or 0) * weight
    return score


def _incremental_score(item: StockEvidenceChainItem) -> int:
    return (8 if item.incremental_valid is True else 0) + min(len(item.incremental_points), 4)


def _diffusion_score(item: StockEvidenceChainItem) -> int:
    return min(item.unique_trigger_count, 12) + min(item.sender_count, 6) * 2 + min(item.conversation_count, 6) * 2


def _reverse_time_key(value: str) -> str:
    return "".join(chr(255 - ord(char)) for char in value)
