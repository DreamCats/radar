from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from radar.core.models import MessageAnchorType, MessageCategory


@dataclass(frozen=True)
class TopicScoreCandidate:
    name: str
    rows: tuple[Mapping[str, Any], ...]
    message_ids: frozenset[str]
    anchor_types: frozenset[MessageAnchorType]
    related_stock_count: int


_CATEGORY_WEIGHTS: dict[MessageCategory, float] = {
    "recommendation": 1.25,
    "research": 1.0,
    "industry": 0.9,
    "event": 0.55,
    "tool_ad": 0.65,
    "chat": 0.1,
    "unknown": 0.1,
}


def topic_score(candidate: TopicScoreCandidate, all_candidates: list[TopicScoreCandidate]) -> float:
    category_score = _average_category_score(candidate.rows)
    average_anchor_confidence = _average_anchor_confidence(candidate.rows)
    base_score = (
        len(candidate.message_ids) * 1.0
        + len(candidate.rows) * 0.18
        + candidate.related_stock_count * 0.15
        + category_score
        + average_anchor_confidence
    )
    return round(base_score * _specificity_multiplier(candidate, all_candidates), 3)


def _average_category_score(rows: tuple[Mapping[str, Any], ...]) -> float:
    if not rows:
        return 0
    return sum(_CATEGORY_WEIGHTS[row["category"]] for row in rows) / len(rows)


def _average_anchor_confidence(rows: tuple[Mapping[str, Any], ...]) -> float:
    if not rows:
        return 0
    return sum(float(row["anchor_confidence"]) for row in rows) / len(rows)


def _specificity_multiplier(
    candidate: TopicScoreCandidate,
    all_candidates: list[TopicScoreCandidate],
) -> float:
    generic_factor = _generic_name_factor(candidate.name, candidate.anchor_types)
    if generic_factor <= 0:
        return 1
    covered_ratio = _covered_by_more_specific_ratio(candidate, all_candidates)
    penalty = min(0.55, generic_factor * covered_ratio * 0.65)
    return 1 - penalty


def _covered_by_more_specific_ratio(
    candidate: TopicScoreCandidate,
    all_candidates: list[TopicScoreCandidate],
) -> float:
    if not candidate.message_ids:
        return 0
    covered: set[str] = set()
    for other in all_candidates:
        if other is candidate or not _looks_more_specific(candidate.name, other.name):
            continue
        overlap = candidate.message_ids & other.message_ids
        if overlap:
            covered.update(overlap)
    return len(covered) / len(candidate.message_ids)


def _looks_more_specific(base_name: str, other_name: str) -> bool:
    base_key = _topic_key(base_name)
    other_key = _topic_key(other_name)
    if len(other_key) <= len(base_key):
        return False
    if base_key and base_key in other_key:
        return True
    return True


def _generic_name_factor(name: str, anchor_types: frozenset[MessageAnchorType]) -> float:
    key = _topic_key(name)
    if not key:
        return 0

    if any("a" <= char <= "z" for char in key):
        factor = 0.15 if len(key) <= 4 else 0.05
    elif len(key) <= 2:
        factor = 0.75
    elif len(key) == 3:
        factor = 0.55
    elif len(key) == 4:
        factor = 0.30
    else:
        factor = 0.10

    if anchor_types == {"industry"}:
        factor += 0.20
    elif "industry" in anchor_types:
        factor += 0.10
    return min(factor, 1.0)


def _topic_key(value: str) -> str:
    return "".join(value.split()).lower()
