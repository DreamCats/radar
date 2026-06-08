from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from radar.core.config import RadarConfig
from radar.core.llm import chat_json_list, resolve_provider
from radar.core.models import RawMessage
from radar.core.runs import fail_run, finish_run, start_run
from radar.core.store import connect, init_db
from radar.core.usecases.source.metrics import (
    SourceExtractBatchError,
    SourceExtractBatchMetric,
    SourceExtractResult,
    TimedBatchResult,
    provider_for_batch,
    provider_stats,
)
from radar.core.usecases.source.models import SourceRelationType, SourceStructure
from radar.core.usecases.source.storage import upsert_source_structures
from radar.core.work_pool import run_resource_work_pool

SOURCE_EXTRACT_TASK = "source_extract"
SOURCE_EXTRACT_PROMPT_VERSION = "source-extract-v1"
SOURCE_EXTRACTOR_VERSION = "source-structure-v1"
SOURCE_EXTRACT_BATCH_SIZE = 24
SOURCE_EXTRACT_MAX_CONCURRENCY = 10
MAX_SOURCE_CONTENT_CHARS = 600
SOURCE_EXTRACT_CATEGORIES = ("research", "industry")
SOURCE_REPLAY_LIMIT = 500

SOURCE_NOISE_TERMS = (
    "会议", "纪要", "电话会", "报名", "直播", "路演", "回放", "纪要合集", "日报", "早报", "复盘",
    "收评", "午评", "公告摘要", "财报摘要",
)

SourceExtractBatchFn = Callable[[RadarConfig, list[RawMessage], str | None], list[SourceStructure]]


def extract_source_structures(
    config: RadarConfig,
    *,
    start_time: datetime,
    end_time: datetime,
    limit: int = SOURCE_REPLAY_LIMIT,
    force: bool = False,
    batch_size: int = SOURCE_EXTRACT_BATCH_SIZE,
    max_concurrency: int = SOURCE_EXTRACT_MAX_CONCURRENCY,
    provider_name: str | None = None,
    provider_names: list[str] | None = None,
    llm_batch_extractor: SourceExtractBatchFn | None = None,
) -> SourceExtractResult:
    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if limit < 1:
        raise ValueError("limit 必须大于 0")
    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    if max_concurrency < 1:
        raise ValueError("max_concurrency 必须大于 0")
    if provider_name and provider_names:
        raise ValueError("provider_name 和 provider_names 只能二选一")

    provider_pool = _provider_pool(config, provider_name=provider_name, provider_names=provider_names)
    metadata = {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "limit": limit,
        "force": force,
        "batch_size": batch_size,
        "max_concurrency": max_concurrency,
        "provider_name": provider_name,
        "provider_names": provider_names,
        "provider_pool": provider_pool,
    }
    run_id = start_run(config.database_path, kind="source_extract", target=f"{start_time.isoformat()}|{end_time.isoformat()}", metadata=metadata)
    conn = connect(config.database_path)
    try:
        init_db(conn)
        messages = _list_extract_candidates(conn, start_time=start_time, end_time=end_time, limit=limit, force=force)
        extracted, inserted, llm_count, failed_batches, actual_concurrency, batch_metrics = _extract_with_llm(
            conn,
            config,
            messages,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            provider_pool=provider_pool,
            llm_batch_extractor=llm_batch_extractor or extract_batch_with_llm,
        )
        result = SourceExtractResult(
            run_id=run_id,
            scanned_count=len(messages),
            extracted_count=len(extracted),
            inserted_count=inserted,
            llm_count=llm_count,
            failed_llm_batches=failed_batches,
            max_concurrency=actual_concurrency,
            provider_pool=provider_pool,
            llm_batch_metrics=batch_metrics,
            failed_llm_batch_details=[item for item in batch_metrics if item.status == "failed"],
            provider_stats=provider_stats(batch_metrics),
        )
        finish_run(config.database_path, run_id, raw_count=len(messages), stored_count=inserted, metadata=metadata | result.model_dump())
        return result
    except Exception as exc:
        fail_run(config.database_path, run_id, exc)
        raise
    finally:
        conn.close()


def extract_batch_with_llm(
    config: RadarConfig,
    batch: list[RawMessage],
    provider_name: str | None,
) -> list[SourceStructure]:
    selected_provider, _ = resolve_provider(config, provider_name=provider_name, task=SOURCE_EXTRACT_TASK)
    items = chat_json_list(
        config,
        _prompt_messages(batch),
        provider_name=selected_provider,
        disable_thinking=True,
    )
    return _normalize_llm_items(batch, items, llm_provider=selected_provider)


def _extract_with_llm(
    conn,
    config: RadarConfig,
    messages: list[RawMessage],
    *,
    batch_size: int,
    max_concurrency: int,
    provider_pool: list[str | None],
    llm_batch_extractor: SourceExtractBatchFn,
) -> tuple[list[SourceStructure], int, int, int, int, list[SourceExtractBatchMetric]]:
    batches = _batches(messages, batch_size)
    if not batches:
        return [], 0, 0, 0, 0, []
    extracted: list[SourceStructure] = []
    inserted_count = 0
    llm_count = 0
    failed_batches = 0
    batch_metrics: list[SourceExtractBatchMetric] = []

    def worker(_index: int, batch: list[RawMessage], provider: str | None) -> TimedBatchResult:
        started = time.monotonic()
        try:
            result = llm_batch_extractor(config, batch, provider)
        except BaseException as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            raise SourceExtractBatchError(provider=provider, elapsed_ms=elapsed_ms, original=exc) from exc
        return TimedBatchResult(items=result, elapsed_ms=int((time.monotonic() - started) * 1000))

    def on_result(index: int, batch: list[RawMessage], result: TimedBatchResult) -> None:
        nonlocal inserted_count, llm_count
        extracted.extend(result.items)
        inserted_count += upsert_source_structures(conn, result.items)
        llm_count += len(result.items)
        batch_metrics.append(
            SourceExtractBatchMetric(
                batch_index=index,
                provider=provider_for_batch(provider_pool, index),
                message_count=len(batch),
                result_count=len(result.items),
                elapsed_ms=result.elapsed_ms,
                status="succeeded",
            )
        )

    def on_error(index: int, batch: list[RawMessage], error: BaseException) -> None:
        nonlocal failed_batches
        failed_batches += 1
        provider = provider_for_batch(provider_pool, index)
        elapsed_ms = 0
        original = error
        if isinstance(error, SourceExtractBatchError):
            provider = error.provider
            elapsed_ms = error.elapsed_ms
            original = error.original
        batch_metrics.append(
            SourceExtractBatchMetric(
                batch_index=index,
                provider=provider,
                message_count=len(batch),
                elapsed_ms=elapsed_ms,
                status="failed",
                error_type=type(original).__name__,
                error_message=str(original)[:300],
            )
        )

    stats = run_resource_work_pool(
        batches,
        resources=provider_pool,
        max_workers=max_concurrency,
        worker=worker,
        on_result=on_result,
        on_error=on_error,
    )
    if failed_batches == len(batches):
        raise RuntimeError("源头结构抽取全部批次失败")
    batch_metrics.sort(key=lambda item: item.batch_index)
    return extracted, inserted_count, llm_count, failed_batches, stats.actual_workers, batch_metrics


def _list_extract_candidates(conn, *, start_time: datetime, end_time: datetime, limit: int, force: bool) -> list[RawMessage]:
    force_clause = "" if force else "AND ss.structure_id IS NULL"
    rows = conn.execute(
        f"""
        SELECT m.*, c.category AS classification_category
        FROM messages m
        JOIN message_classifications c ON c.message_id = m.message_id
        LEFT JOIN source_structures ss
          ON ss.message_id = m.message_id AND ss.extractor_version = ?
        WHERE m.message_time >= ?
          AND m.message_time <= ?
          AND c.category IN ({','.join('?' for _ in SOURCE_EXTRACT_CATEGORIES)})
          AND c.confidence >= 0.65
          AND c.status != 'ignored'
          {force_clause}
        ORDER BY m.message_time ASC, m.message_id ASC
        """,
        (SOURCE_EXTRACTOR_VERSION, start_time.isoformat(), end_time.isoformat(), *SOURCE_EXTRACT_CATEGORIES),
    ).fetchall()
    ranked = []
    for row in rows:
        message = _message_from_row(row)
        score = _source_candidate_score(message.raw_content, str(row["classification_category"] or ""))
        if score > 0:
            ranked.append((score, message.message_time, message.message_id, message))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [item[3] for item in ranked[:limit]]


def _message_from_row(row) -> RawMessage:
    return RawMessage(
        message_id=str(row["message_id"]),
        source=str(row["source"]),  # type: ignore[arg-type]
        sender=str(row["sender"]),
        message_time=datetime.fromisoformat(str(row["message_time"])),
        raw_content=str(row["raw_content"]),
        group_name=str(row["group_name"]) if row["group_name"] else None,
        fetch_time=datetime.fromisoformat(str(row["fetch_time"])),
        fetch_window=str(row["fetch_window"]),
    )


def _source_candidate_score(content: str, category: str) -> float:
    text = content[:1200]
    if any(term in text for term in SOURCE_NOISE_TERMS):
        return 0.0
    score = 1.0
    if category == "event":
        score += 1.2
    elif category == "industry":
        score += 0.8
    elif category == "research":
        score += 0.2
    return score


def _prompt_messages(batch: list[RawMessage]) -> list[dict[str, str]]:
    lines = []
    for index, message in enumerate(batch, 1):
        lines.append(
            f"[{index}] time={message.message_time.isoformat()} source={message.source} "
            f"group={message.group_name or '-'} sender={message.sender}\n"
            f"{message.raw_content[:MAX_SOURCE_CONTENT_CHARS]}"
        )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "请从以下消息抽取源头概念结构，返回 JSON 数组：\n\n" + "\n\n".join(lines)},
    ]


def _normalize_llm_items(batch: list[RawMessage], items: list[dict[str, Any]], *, llm_provider: str | None) -> list[SourceStructure]:
    now = datetime.now()
    messages_by_index = {index: message for index, message in enumerate(batch, 1)}
    out: list[SourceStructure] = []
    for item in items:
        index = _as_int(item.get("index"))
        if index is None or index not in messages_by_index:
            continue
        message = messages_by_index[index]
        is_candidate = bool(item.get("is_candidate"))
        anchor = _clean_span(item.get("anchor_span"))
        modifier = _clean_span(item.get("modifier_span"))
        novel = _clean_span(item.get("novel_span"))
        if is_candidate and (not anchor or not modifier or not novel):
            is_candidate = False
        relation = _relation(item.get("relation_type"))
        out.append(
            SourceStructure(
                structure_id=_structure_id(message.message_id, anchor, modifier, novel, relation),
                message_id=message.message_id,
                source=message.source,
                sender=message.sender,
                group_name=message.group_name,
                message_time=message.message_time,
                is_candidate=is_candidate,
                anchor_span=anchor,
                modifier_span=modifier,
                novel_span=novel,
                relation_type=relation,
                relation_evidence=str(item.get("relation_evidence") or "")[:300],
                ask_question=str(item.get("ask_question") or "")[:300],
                confidence=_confidence(item.get("confidence")),
                reject_reason=str(item.get("reject_reason") or "")[:200] or None,
                llm_provider=llm_provider,
                prompt_version=SOURCE_EXTRACT_PROMPT_VERSION,
                extractor_version=SOURCE_EXTRACTOR_VERSION,
                created_at=now,
                updated_at=now,
            )
        )
    return out


def _provider_pool(config: RadarConfig, *, provider_name: str | None, provider_names: list[str] | None) -> list[str | None]:
    if provider_names:
        return provider_names
    if provider_name:
        return [provider_name]
    if config.llm.providers:
        return list(config.llm.providers)
    selected_name, _ = resolve_provider(config, task=SOURCE_EXTRACT_TASK)
    return [selected_name]


def _batches(messages: list[RawMessage], batch_size: int) -> list[list[RawMessage]]:
    return [messages[index : index + batch_size] for index in range(0, len(messages), batch_size)]


def _clean_span(value: object) -> str:
    return "".join(str(value or "").strip().split())


def _relation(value: object) -> SourceRelationType:
    text = str(value or "other")
    return text if text in {"A化B", "prefix-anchor", "modifier-anchor", "anchor-extension", "other"} else "other"  # type: ignore[return-value]


def _confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(str(value))))
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _structure_id(message_id: str, anchor: str, modifier: str, novel: str, relation: str) -> str:
    raw = "|".join([message_id, anchor, modifier, novel, relation, SOURCE_EXTRACTOR_VERSION])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


_SYSTEM_PROMPT = """你是投研消息的源头概念结构抽取器。
只做可回指原文的 span 抽取，不判断新不新、早不早、会不会涨。

目标：寻找“成熟锚点 + 陌生修饰/新关系”的组合表达。
示例：PCB + 半导体化 => 半导体化的PCB；AI + 电源 => AI电源。

返回 JSON 数组，每条包含：
index, is_candidate, anchor_span, modifier_span, novel_span, relation_type,
relation_evidence, ask_question, confidence, reject_reason。

要求：
- anchor_span、modifier_span、novel_span 必须能在原文中定位或由原文连续短语轻微规范化得到。
- 不要输出总结词、脑补词、泛概念词。
- 如果只是普通股票推荐、会议通知、复盘摘要，is_candidate=false。
- relation_type 只能是 A化B、prefix-anchor、modifier-anchor、anchor-extension、other。
"""
