from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from radar.core.models import MessageAnchor, MessageAnchorType, RawMessage
from radar.core.usecases.anchoring.dictionary import AnchorDictionary, AnchorTerm

ANCHOR_EXTRACTOR_VERSION = "anchor-dict-v2"
Segmenter = Callable[[str], Iterable[str]]

_BASE_CONFIDENCE: dict[MessageAnchorType, float] = {
    "stock": 0.98,
    "concept": 0.90,
    "industry": 0.86,
    "theme": 0.84,
}


def extract_message_anchors(
    message: RawMessage,
    dictionary: AnchorDictionary,
    *,
    segmenter: Segmenter | None = None,
    extractor_version: str = ANCHOR_EXTRACTOR_VERSION,
    max_anchors: int = 12,
) -> list[MessageAnchor]:
    """抽取单条消息里的市场 anchor；第一版只做确定性词库命中。"""

    if max_anchors < 1:
        raise ValueError("max_anchors 必须大于 0")

    content = message.raw_content or ""
    content_lower = content.lower()
    token_set = _tokens(content, segmenter)
    matches: dict[str, tuple[AnchorTerm, float, dict[str, object]]] = {}

    for term in dictionary.terms:
        evidence = _direct_evidence(content, content_lower, term.term)
        match_type = "exact"
        if evidence is None and term.term.lower() in token_set:
            evidence = {"text": term.term, "match_type": "token"}
            match_type = "token"
        if evidence is None:
            continue

        confidence = _confidence(term, match_type)
        previous = matches.get(term.anchor_id)
        if previous is None or confidence > previous[1]:
            matches[term.anchor_id] = (term, confidence, evidence)

    now = datetime.now()
    anchors = [
        MessageAnchor(
            message_id=message.message_id,
            anchor_id=term.anchor_id,
            anchor_type=term.anchor_type,
            name=term.name,
            confidence=confidence,
            evidence=[evidence],
            extractor_version=extractor_version,
            trade_date=dictionary.trade_date,
            created_at=now,
            updated_at=now,
        )
        for term, confidence, evidence in matches.values()
    ]
    anchors.sort(key=lambda item: (-item.confidence, _type_rank(item.anchor_type), item.name))
    return anchors[:max_anchors]


def _direct_evidence(content: str, content_lower: str, term: str) -> dict[str, object] | None:
    lower_term = term.lower()
    start = content_lower.find(lower_term)
    while start >= 0:
        end = start + len(term)
        if _valid_match_boundary(content, start, end, term):
            return {"text": content[start:end], "match_type": "exact", "start": start}
        start = content_lower.find(lower_term, start + 1)
    return None


def _valid_match_boundary(content: str, start: int, end: int, term: str) -> bool:
    if not any(char.isascii() and char.isalnum() for char in term):
        return True
    before = content[start - 1] if start > 0 else ""
    after = content[end] if end < len(content) else ""
    return not _ascii_word_char(before) and not _ascii_word_char(after)


def _ascii_word_char(value: str) -> bool:
    return value.isascii() and (value.isalnum() or value == "_")


def _tokens(content: str, segmenter: Segmenter | None) -> set[str]:
    if segmenter is None:
        return set()
    return {str(token).strip().lower() for token in segmenter(content) if str(token).strip()}


def _confidence(term: AnchorTerm, match_type: str) -> float:
    score = _BASE_CONFIDENCE[term.anchor_type]
    if term.term_kind == "alias":
        score -= 0.04
    if match_type == "token":
        score -= 0.06
    if term.anchor_type != "stock" and len(term.term) <= 2:
        score -= 0.08
    return max(0.50, min(0.99, round(score, 2)))


def _type_rank(anchor_type: MessageAnchorType) -> int:
    return {"stock": 0, "concept": 1, "industry": 2, "theme": 3}[anchor_type]
