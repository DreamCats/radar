from __future__ import annotations

import math
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from radar.core.models import MessageAnchor, MessageAnchorType

_TYPE_WEIGHTS: dict[MessageAnchorType, float] = {
    "stock": 1.12,
    "concept": 1.00,
    "industry": 0.88,
    "theme": 0.84,
}


@dataclass(frozen=True)
class AnchorRankingConfig:
    max_anchors_per_message: int = 7
    max_stock_anchors: int = 3
    max_topic_anchors: int = 4
    fuzzy_name_threshold: float = 96.0
    min_score: float = 0.52


def rank_anchor_batch(
    anchors_by_message: dict[str, list[MessageAnchor]],
    *,
    config: AnchorRankingConfig | None = None,
) -> dict[str, list[MessageAnchor]]:
    """归一和排序一批消息 anchor；算法层不依赖数据库和外部服务。"""

    ranking_config = config or AnchorRankingConfig()
    if ranking_config.max_anchors_per_message < 1:
        raise ValueError("max_anchors_per_message 必须大于 0")
    if ranking_config.max_stock_anchors < 0:
        raise ValueError("max_stock_anchors 不能小于 0")
    if ranking_config.max_topic_anchors < 0:
        raise ValueError("max_topic_anchors 不能小于 0")

    document_frequencies = _document_frequencies(anchors_by_message)
    document_count = max(1, len(anchors_by_message))
    ranked: dict[str, list[MessageAnchor]] = {}
    for message_id, anchors in anchors_by_message.items():
        canonical = _canonicalize_message_anchors(
            anchors,
            fuzzy_name_threshold=ranking_config.fuzzy_name_threshold,
        )
        scored = [
            _with_rank_score(
                item,
                document_frequency=document_frequencies.get(_document_key(item), 1),
                document_count=document_count,
            )
            for item in canonical
        ]
        filtered = [item for item in scored if item.confidence >= ranking_config.min_score]
        ranked[message_id] = _select_bucketed_anchors(filtered, ranking_config)
    return ranked


def _select_bucketed_anchors(
    anchors: list[MessageAnchor],
    config: AnchorRankingConfig,
) -> list[MessageAnchor]:
    stock_anchors = _sort_bucket([item for item in anchors if item.anchor_type == "stock"])
    topic_anchors = _sort_bucket([item for item in anchors if item.anchor_type != "stock"])
    stock_limit = _stock_limit(config)
    topic_limit = min(config.max_topic_anchors, config.max_anchors_per_message - stock_limit)
    selected = [
        *topic_anchors[:topic_limit],
        *stock_anchors[:stock_limit],
    ]
    return selected


def _stock_limit(config: AnchorRankingConfig) -> int:
    if config.max_stock_anchors == 0:
        return 0
    if config.max_topic_anchors == 0:
        return min(config.max_stock_anchors, config.max_anchors_per_message)
    reserved = max(1, config.max_anchors_per_message - config.max_topic_anchors)
    return min(config.max_stock_anchors, config.max_anchors_per_message, reserved)


def _sort_bucket(anchors: list[MessageAnchor]) -> list[MessageAnchor]:
    return sorted(
        anchors,
        key=lambda item: (
            -item.confidence,
            _type_rank(item.anchor_type),
            -len(item.name),
            item.name,
        ),
    )


def _canonicalize_message_anchors(
    anchors: list[MessageAnchor],
    *,
    fuzzy_name_threshold: float,
) -> list[MessageAnchor]:
    canonical: list[MessageAnchor] = []
    for anchor in sorted(
        anchors,
        key=lambda item: (-item.confidence, _type_rank(item.anchor_type), item.name),
    ):
        match_index = _matching_canonical_index(canonical, anchor, fuzzy_name_threshold)
        if match_index is None:
            canonical.append(anchor)
            continue
        canonical[match_index] = _merge_duplicate(canonical[match_index], anchor)
    return canonical


def _matching_canonical_index(
    canonical: list[MessageAnchor],
    anchor: MessageAnchor,
    fuzzy_name_threshold: float,
) -> int | None:
    if anchor.anchor_type == "stock":
        return None
    normalized = _normalize_name(anchor.name)
    for index, item in enumerate(canonical):
        if item.anchor_type == "stock":
            continue
        item_normalized = _normalize_name(item.name)
        if normalized == item_normalized:
            return index
        if fuzz.ratio(normalized, item_normalized) >= fuzzy_name_threshold:
            return index
    return None


def _merge_duplicate(current: MessageAnchor, duplicate: MessageAnchor) -> MessageAnchor:
    winner = _better_anchor(current, duplicate)
    loser = duplicate if winner is current else current
    evidence = [*winner.evidence, *_duplicate_evidence(loser)]
    return winner.model_copy(update={"evidence": evidence})


def _better_anchor(left: MessageAnchor, right: MessageAnchor) -> MessageAnchor:
    left_key = (left.confidence, -_type_rank(left.anchor_type), len(left.name))
    right_key = (right.confidence, -_type_rank(right.anchor_type), len(right.name))
    return left if left_key >= right_key else right


def _duplicate_evidence(anchor: MessageAnchor) -> list[dict[str, object]]:
    return [
        {
            "match_type": "canonical_duplicate",
            "anchor_id": anchor.anchor_id,
            "anchor_type": anchor.anchor_type,
            "name": anchor.name,
            "confidence": anchor.confidence,
        }
    ]


def _with_rank_score(
    anchor: MessageAnchor,
    *,
    document_frequency: int,
    document_count: int,
) -> MessageAnchor:
    score = anchor.confidence
    score *= _TYPE_WEIGHTS[anchor.anchor_type]
    score *= _specificity_weight(anchor)
    score *= _idf_weight(document_frequency, document_count)
    score = max(0.0, min(0.99, round(score, 3)))
    evidence = [
        *anchor.evidence,
        {
            "match_type": "local_rank",
            "raw_confidence": anchor.confidence,
            "document_frequency": document_frequency,
            "document_count": document_count,
        },
    ]
    return anchor.model_copy(update={"confidence": score, "evidence": evidence})


def _document_frequencies(anchors_by_message: dict[str, list[MessageAnchor]]) -> dict[str, int]:
    frequencies: dict[str, int] = {}
    for anchors in anchors_by_message.values():
        for key in {_document_key(anchor) for anchor in anchors}:
            frequencies[key] = frequencies.get(key, 0) + 1
    return frequencies


def _document_key(anchor: MessageAnchor) -> str:
    if anchor.anchor_type == "stock":
        return anchor.anchor_id
    return f"non_stock:{_normalize_name(anchor.name)}"


def _specificity_weight(anchor: MessageAnchor) -> float:
    if anchor.anchor_type == "stock":
        return 1.10
    normalized = _normalize_name(anchor.name)
    if len(normalized) <= 2:
        return 0.76
    if len(normalized) <= 3:
        return 0.90
    return 1.0


def _idf_weight(document_frequency: int, document_count: int) -> float:
    idf = math.log((document_count + 1) / (document_frequency + 1)) + 1
    return max(0.72, min(1.12, idf / 2.0 + 0.58))


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _type_rank(anchor_type: MessageAnchorType) -> int:
    return {"stock": 0, "concept": 1, "industry": 2, "theme": 3}[anchor_type]
