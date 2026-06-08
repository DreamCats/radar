from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz

from radar.core.config import RadarConfig
from radar.core.llm import resolve_provider
from radar.core.models import MessageCategory, MessageSource
from radar.core.runs import fail_run, finish_run, start_run
from radar.core.store import connect, init_db
from radar.core.usecases.categories import normalize_derived_input_categories
from radar.core.usecases.aggregation.models import (
    AggregateTopic,
    RefineAggregateTopicsResult,
    RefinedTheme,
    RefinedThemeStock,
)
from radar.core.usecases.aggregation.prompts import REFINE_PROMPT_VERSION
from radar.core.usecases.aggregation.refine_llm import refine_batch_with_llm
from radar.core.usecases.aggregation.storage import load_refine_result, store_refine_result
from radar.core.usecases.aggregation.topics import aggregate_topics
from radar.core.usecases.anchoring import ANCHOR_EXTRACTOR_VERSION
from radar.core.work_pool import run_work_pool

REFINE_TASK = "aggregate_refine"
REFINE_CANDIDATE_LIMIT = 50
REFINE_BATCH_SIZE = 5
REFINE_MAX_CONCURRENCY = 10
MAX_REFINE_EVIDENCE_CHARS = 520

RefineBatchFn = Callable[[RadarConfig, list[dict[str, Any]], str | None], list[RefinedTheme]]


def refine_aggregate_topics(
    config: RadarConfig,
    *,
    trade_date: str,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None = None,
    categories: list[MessageCategory] | None = None,
    min_classification_confidence: float = 0.7,
    extractor_version: str = ANCHOR_EXTRACTOR_VERSION,
    min_messages: int = 2,
    candidate_limit: int = REFINE_CANDIDATE_LIMIT,
    evidence_limit: int = 3,
    batch_size: int = REFINE_BATCH_SIZE,
    max_concurrency: int = REFINE_MAX_CONCURRENCY,
    provider_name: str | None = None,
    provider_names: list[str] | None = None,
    force: bool = False,
    run_id: str | None = None,
    llm_batch_refiner: RefineBatchFn | None = None,
) -> RefineAggregateTopicsResult:
    """对本地聚合候选做 LLM refinement；使用输入 hash 支持增量跳过。"""

    _validate_refine_inputs(candidate_limit, evidence_limit, batch_size, max_concurrency)
    category_values = normalize_derived_input_categories(categories)
    local_result = aggregate_topics(
        config,
        trade_date=trade_date,
        start_time=start_time,
        end_time=end_time,
        source=source,
        categories=category_values,
        min_classification_confidence=min_classification_confidence,
        extractor_version=extractor_version,
        min_messages=min_messages,
        limit=candidate_limit,
        evidence_limit=evidence_limit,
    )
    candidates = _candidate_inputs(local_result.topics)
    provider_pool = _provider_pool(
        config,
        provider_name=provider_name,
        provider_names=provider_names,
        resolve_default=bool(candidates) and llm_batch_refiner is None,
    )
    input_hash = _input_hash(
        trade_date=trade_date,
        start_time=start_time,
        end_time=end_time,
        source=source,
        categories=category_values,
        min_classification_confidence=min_classification_confidence,
        extractor_version=extractor_version,
        min_messages=min_messages,
        candidate_limit=candidate_limit,
        evidence_limit=evidence_limit,
        provider_pool=provider_pool,
        candidates=candidates,
    )

    run_metadata = {
        "trade_date": trade_date,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "source": source,
        "categories": category_values,
        "candidate_limit": candidate_limit,
        "evidence_limit": evidence_limit,
        "batch_size": batch_size,
        "max_concurrency": max_concurrency,
        "provider_name": provider_name,
        "provider_names": provider_names,
        "input_hash": input_hash,
        "force": force,
    }

    conn = connect(config.database_path)
    try:
        init_db(conn)
        if not force:
            cached = load_refine_result(conn, input_hash)
            if cached is not None:
                result = cached.model_copy(update={"status": "skipped", "run_id": run_id or cached.run_id})
                if run_id is not None:
                    finish_run(
                        config.database_path,
                        run_id,
                        status="skipped",
                        raw_count=result.candidate_count,
                        stored_count=result.theme_count,
                        metadata=run_metadata | result.model_dump(exclude={"local_result", "themes"}),
                    )
                return result
    finally:
        conn.close()

    if run_id is None:
        run_id = start_run(
            config.database_path,
            kind=REFINE_TASK,
            target=_run_target(trade_date, start_time, end_time, source),
            metadata=run_metadata,
        )
    try:
        themes, failed_batches, actual_concurrency = _refine_candidates(
            config,
            candidates,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            provider_pool=provider_pool,
            llm_batch_refiner=llm_batch_refiner or refine_batch_with_llm,
        )
        result = RefineAggregateTopicsResult(
            run_id=run_id,
            input_hash=input_hash,
            status="succeeded",
            trade_date=trade_date,
            extractor_version=extractor_version,
            prompt_version=REFINE_PROMPT_VERSION,
            candidate_count=len(candidates),
            theme_count=len(themes),
            llm_batch_count=len(_batches(candidates, batch_size)),
            failed_llm_batches=failed_batches,
            max_concurrency=actual_concurrency,
            local_result=local_result,
            themes=themes,
        )
        conn = connect(config.database_path)
        try:
            init_db(conn)
            store_refine_result(conn, result)
        finally:
            conn.close()
        finish_run(
            config.database_path,
            run_id,
            raw_count=len(candidates),
            stored_count=len(themes),
            filtered_count=failed_batches,
            metadata=run_metadata | result.model_dump(exclude={"local_result", "themes"}),
        )
        return result
    except Exception as exc:
        fail_run(config.database_path, run_id, exc)
        raise


def _refine_candidates(
    config: RadarConfig,
    candidates: list[dict[str, Any]],
    *,
    batch_size: int,
    max_concurrency: int,
    provider_pool: list[str | None],
    llm_batch_refiner: RefineBatchFn,
) -> tuple[list[RefinedTheme], int, int]:
    batches = _batches(candidates, batch_size)
    if not batches:
        return [], 0, 0

    themes: list[RefinedTheme] = []
    failed_batches = 0

    def worker(index: int, batch: list[dict[str, Any]]) -> list[RefinedTheme]:
        return llm_batch_refiner(config, batch, provider_pool[index % len(provider_pool)])

    def on_result(_index: int, _batch: list[dict[str, Any]], result: list[RefinedTheme]) -> None:
        themes.extend(result)

    def on_error(_index: int, _batch: list[dict[str, Any]], _error: BaseException) -> None:
        nonlocal failed_batches
        failed_batches += 1

    stats = run_work_pool(
        batches,
        max_workers=max_concurrency,
        worker=worker,
        on_result=on_result,
        on_error=on_error,
    )
    if failed_batches == len(batches):
        raise RuntimeError("LLM refine 全部批次失败")
    return _merge_themes(themes), failed_batches, stats.actual_workers


def _candidate_inputs(topics: list[AggregateTopic]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, topic in enumerate(topics, start=1):
        candidates.append(
            {
                "candidate_id": f"c{index}",
                "local_name": topic.name,
                "local_score": topic.score,
                "message_count": topic.message_count,
                "anchor_count": topic.anchor_count,
                "anchor_types": topic.anchor_types,
                "stock_names": [item.name for item in topic.related_stocks],
                "category_distribution": topic.category_distribution,
                "evidence": [
                    {
                        "message_id": item.message_id,
                        "time": item.message_time.isoformat(),
                        "category": item.category,
                        "sender": item.sender,
                        "group_name": item.group_name,
                        "text": _compact_evidence(item.raw_content),
                        "stocks": item.stocks,
                    }
                    for item in topic.evidence
                ],
            }
        )
    return candidates


def _merge_themes(themes: list[RefinedTheme]) -> list[RefinedTheme]:
    merged: dict[str, RefinedTheme] = {}
    for theme in themes:
        key = _merge_key(theme, merged)
        existing = merged.get(key)
        if existing is None:
            merged[key] = theme
            continue
        merged[key] = existing.model_copy(
            update={
                "aliases": _unique(existing.aliases + theme.aliases),
                "catalysts": _unique(existing.catalysts + theme.catalysts),
                "related_stocks": _merge_stocks(existing.related_stocks + theme.related_stocks),
                "evidence_message_ids": _unique(existing.evidence_message_ids + theme.evidence_message_ids),
                "risk_notes": _unique(existing.risk_notes + theme.risk_notes),
                "merge_from_candidate_ids": _unique(existing.merge_from_candidate_ids + theme.merge_from_candidate_ids),
                "confidence": max(existing.confidence, theme.confidence),
                "actionability_score": max(existing.actionability_score, theme.actionability_score),
            }
        )
    return sorted(merged.values(), key=lambda item: (-item.actionability_score, -item.confidence, item.theme_name))


def _merge_key(theme: RefinedTheme, merged: dict[str, RefinedTheme]) -> str:
    key = _theme_key(theme.theme_name)
    if key in merged:
        return key
    for existing_key, existing in merged.items():
        if _should_merge_theme(existing, theme):
            return existing_key
    return key


def _should_merge_theme(left: RefinedTheme, right: RefinedTheme) -> bool:
    name_similarity = fuzz.ratio(_theme_key(left.theme_name), _theme_key(right.theme_name))
    if name_similarity >= 78:
        return True
    left_evidence = set(left.evidence_message_ids)
    right_evidence = set(right.evidence_message_ids)
    if not left_evidence or not right_evidence:
        return False
    overlap = len(left_evidence & right_evidence) / min(len(left_evidence), len(right_evidence))
    return overlap >= 0.5 and name_similarity >= 45


def _provider_pool(
    config: RadarConfig,
    *,
    provider_name: str | None,
    provider_names: list[str] | None,
    resolve_default: bool,
) -> list[str | None]:
    if provider_names:
        return provider_names
    if provider_name:
        return [provider_name]
    if not resolve_default:
        return [None]
    selected_name, _ = resolve_provider(config, task=REFINE_TASK)
    return [selected_name]


def _input_hash(**payload: Any) -> str:
    payload = payload | {"prompt_version": REFINE_PROMPT_VERSION}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _batches(items: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _merge_stocks(stocks: list[RefinedThemeStock]) -> list[RefinedThemeStock]:
    merged: dict[str, RefinedThemeStock] = {}
    for stock in stocks:
        existing = merged.get(stock.name)
        if existing is None or stock.confidence > existing.confidence:
            merged[stock.name] = stock
    return sorted(merged.values(), key=lambda item: (-item.confidence, item.name))


def _unique(items: list[str] | Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _compact_evidence(value: str) -> str:
    text = " ".join(value.split())
    if len(text) <= MAX_REFINE_EVIDENCE_CHARS:
        return text
    return text[: MAX_REFINE_EVIDENCE_CHARS - 1] + "…"


def _theme_key(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _run_target(
    trade_date: str,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None,
) -> str:
    return "|".join([trade_date, source or "all", start_time.isoformat(), end_time.isoformat()])


def _validate_refine_inputs(
    candidate_limit: int,
    evidence_limit: int,
    batch_size: int,
    max_concurrency: int,
) -> None:
    if candidate_limit < 1:
        raise ValueError("candidate_limit 必须大于 0")
    if evidence_limit < 0:
        raise ValueError("evidence_limit 不能小于 0")
    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    if max_concurrency < 1:
        raise ValueError("max_concurrency 必须大于 0")
