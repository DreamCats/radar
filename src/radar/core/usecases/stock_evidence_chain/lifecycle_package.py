from __future__ import annotations

from datetime import datetime
from typing import Any

from radar.core.usecases.stock_evidence_chain.view_models import StockEvidenceChainItem

PROMPT_VERSION = "opportunity-lifecycle-digest-v2"


def evidence_package(item: StockEvidenceChainItem, *, as_of_time: datetime | None) -> dict[str, Any]:
    theme = item.primary_theme
    return {
        "prompt_version": PROMPT_VERSION,
        "as_of_time": as_of_time.isoformat() if as_of_time else None,
        "stock": {"ts_code": item.ts_code, "stock_name": item.stock_name},
        "theme": theme.model_dump(mode="json") if theme else None,
        "theme_candidates": [theme.model_dump(mode="json") for theme in item.themes[:4]],
        "stage": {"code": item.stage, "label": item.stage_label, "confidence": item.confidence, "why": item.why},
        "recognition": item.recognition.model_dump(mode="json"),
        "review": item.review.model_dump(mode="json"),
        "message_evidence": {
            "trigger_count": item.trigger_count,
            "unique_trigger_count": item.unique_trigger_count,
            "sender_count": item.sender_count,
            "conversation_count": item.conversation_count,
            "family_counts": item.family_counts,
            "timeline": [point.model_dump(mode="json") for point in item.evidence_chain[:8]],
        },
        "market_evidence": {
            "summary": item.market_summary,
            "points": [point.model_dump(mode="json") for point in item.market_points[-6:]],
        },
        "risks": {
            "pricing_risk": item.pricing_risk,
            "crowding_risk": item.crowding_risk,
            "watch_next": item.watch_next,
        },
    }
