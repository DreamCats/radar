from __future__ import annotations

import json
from typing import Any, cast

from radar.core.config import RadarConfig
from radar.core.llm import chat_json_list
from radar.core.usecases.aggregation.models import RefinedTheme, RefinedThemeStock
from radar.core.usecases.aggregation.prompts import REFINE_SYSTEM_PROMPT

REFINE_TASK = "aggregate_refine"


def refine_batch_with_llm(
    config: RadarConfig,
    candidates: list[dict[str, Any]],
    provider_name: str | None,
) -> list[RefinedTheme]:
    items = chat_json_list(
        config,
        _prompt_messages(candidates),
        provider_name=provider_name,
        task=REFINE_TASK,
        disable_thinking=True,
    )
    return _normalize_themes(
        items,
        allowed_candidate_ids=_candidate_ids(candidates),
        allowed_message_ids=_message_ids(candidates),
    )


def _prompt_messages(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": REFINE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "以下是本地聚合候选主题，请做投资视角 refinement：\n"
            + json.dumps(candidates, ensure_ascii=False, sort_keys=True),
        },
    ]


def _normalize_themes(
    items: list[dict[str, object]],
    *,
    allowed_candidate_ids: set[str],
    allowed_message_ids: set[str],
) -> list[RefinedTheme]:
    themes: list[RefinedTheme] = []
    for item in items:
        theme_name = str(item.get("theme_name") or "").strip()
        if not theme_name:
            continue
        themes.append(
            RefinedTheme(
                theme_name=theme_name,
                aliases=_string_list(item.get("aliases")),
                summary=str(item.get("summary") or "").strip(),
                investment_logic=str(item.get("investment_logic") or "").strip(),
                catalysts=_string_list(item.get("catalysts")),
                related_stocks=_stocks(item.get("related_stocks")),
                evidence_message_ids=[
                    message_id
                    for message_id in _string_list(item.get("evidence_message_ids"))
                    if message_id in allowed_message_ids
                ],
                novelty=_novelty(item.get("novelty")),
                confidence=_float_range(item.get("confidence"), default=0.0, min_value=0.0, max_value=1.0),
                actionability_score=_actionability_score(item.get("actionability_score")),
                risk_notes=_string_list(item.get("risk_notes")),
                merge_from_candidate_ids=[
                    candidate_id
                    for candidate_id in _string_list(item.get("merge_from_candidate_ids"))
                    if candidate_id in allowed_candidate_ids
                ],
            )
        )
    return themes


def _candidate_ids(candidates: list[dict[str, Any]]) -> set[str]:
    return {str(item["candidate_id"]) for item in candidates}


def _message_ids(candidates: list[dict[str, Any]]) -> set[str]:
    message_ids: set[str] = set()
    for candidate in candidates:
        for evidence in cast(list[dict[str, object]], candidate.get("evidence", [])):
            message_ids.add(str(evidence.get("message_id") or ""))
    return message_ids


def _stocks(value: object) -> list[RefinedThemeStock]:
    stocks: list[RefinedThemeStock] = []
    if not isinstance(value, list):
        return stocks
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            stocks.append(
                RefinedThemeStock(
                    name=name,
                    reason=str(item.get("reason") or "").strip(),
                    confidence=_float_range(item.get("confidence"), default=0.0, min_value=0.0, max_value=1.0),
                )
            )
        else:
            name = str(item).strip()
            if name:
                stocks.append(RefinedThemeStock(name=name))
    return _merge_stocks(stocks)


def _merge_stocks(stocks: list[RefinedThemeStock]) -> list[RefinedThemeStock]:
    merged: dict[str, RefinedThemeStock] = {}
    for stock in stocks:
        existing = merged.get(stock.name)
        if existing is None or stock.confidence > existing.confidence:
            merged[stock.name] = stock
    return sorted(merged.values(), key=lambda item: (-item.confidence, item.name))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return _unique(str(item).strip() for item in value if str(item).strip())


def _unique(items: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _float_range(value: object, *, default: float, min_value: float, max_value: float) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        number = default
    return round(min(max(number, min_value), max_value), 3)


def _actionability_score(value: object) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return 0.0
    if 0 < number <= 1:
        number *= 100
    elif 1 < number <= 10:
        number *= 10
    return round(min(max(number, 0.0), 100.0), 3)


def _novelty(value: object) -> str:
    text = str(value or "unknown")
    return text if text in {"new", "continuing", "repeated_noise", "unknown"} else "unknown"
