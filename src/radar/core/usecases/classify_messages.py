from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from sqlite3 import Connection
from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.llm import chat_json_list, resolve_provider
from radar.core.models import (
    ClassificationStatus,
    MessageCategory,
    MessageClassification,
    MessageSource,
    RawMessage,
)
from radar.core.runs import fail_run, finish_run, start_run
from radar.core.usecases.classify_prompts import CLASSIFY_SYSTEM_PROMPT
from radar.core.store import (
    connect,
    init_db,
    list_messages_for_classification,
    upsert_message_classifications,
)
from radar.core.work_pool import run_work_pool

CLASSIFY_BATCH_SIZE = 16
CLASSIFY_PROMPT_VERSION = "classify-batch-v2"
CLASSIFY_TASK = "classify"
CLASSIFIER_VERSION = "llm-v2"
CLASSIFY_MAX_CONCURRENCY = 10
MAX_LLM_CONTENT_CHARS = 800
NEEDS_REVIEW_THRESHOLD = 0.65

ClassifyBatchFn = Callable[
    [RadarConfig, list[RawMessage], str | None],
    list[MessageClassification],
]

_CATEGORIES: set[MessageCategory] = {
    "research",
    "recommendation",
    "event",
    "industry",
    "tool_ad",
    "chat",
    "unknown",
}


class ClassifyMessagesResult(BaseModel):
    run_id: str
    scanned_count: int = 0
    classified_count: int = 0
    inserted_count: int = 0
    max_concurrency: int = 0
    llm_count: int = 0
    rule_count: int = 0
    failed_llm_batches: int = 0
    distribution: dict[str, int] = Field(default_factory=dict)
    status_distribution: dict[str, int] = Field(default_factory=dict)


def classify_messages(
    config: RadarConfig,
    *,
    source: MessageSource | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 500,
    force: bool = False,
    use_llm: bool = True,
    provider_name: str | None = None,
    provider_names: list[str] | None = None,
    batch_size: int = CLASSIFY_BATCH_SIZE,
    max_concurrency: int | None = None,
    llm_batch_classifier: ClassifyBatchFn | None = None,
) -> ClassifyMessagesResult:
    """编排消息分类：读取候选、LLM 分类、失败降级为待复核。"""

    if limit < 1:
        raise ValueError("limit 必须大于 0")
    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    if max_concurrency is not None and max_concurrency < 1:
        raise ValueError("max_concurrency 必须大于 0")

    run_metadata = {
        "source": source,
        "start_time": start_time.isoformat() if start_time else None,
        "end_time": end_time.isoformat() if end_time else None,
        "limit": limit,
        "force": force,
        "use_llm": use_llm,
        "provider_name": provider_name,
        "provider_names": provider_names,
        "batch_size": batch_size,
        "max_concurrency": max_concurrency or CLASSIFY_MAX_CONCURRENCY,
    }
    run_id = start_run(
        config.database_path,
        kind="message_classify",
        target=_run_target(source, start_time, end_time),
        metadata=run_metadata,
    )

    conn = connect(config.database_path)
    try:
        init_db(conn)
        messages = list_messages_for_classification(
            conn,
            source=source,
            start_time=start_time.isoformat() if start_time else None,
            end_time=end_time.isoformat() if end_time else None,
            limit=limit,
            force=force,
        )
        if use_llm and messages:
            final_results, inserted_count, llm_count, failed_llm_batches, actual_concurrency = _classify_with_llm(
                conn,
                config,
                messages,
                provider_name=provider_name,
                provider_names=provider_names,
                batch_size=batch_size,
                max_concurrency=max_concurrency,
                llm_batch_classifier=llm_batch_classifier or classify_batch_with_llm,
            )
        else:
            final_results = [_unknown_classification(message, reason="未启用 LLM 分类") for message in messages]
            inserted_count = upsert_message_classifications(conn, final_results)
            llm_count = 0
            failed_llm_batches = 0
            actual_concurrency = 0

        distribution = Counter(item.category for item in final_results)
        status_distribution = Counter(item.status for item in final_results)
        result = ClassifyMessagesResult(
            run_id=run_id,
            scanned_count=len(messages),
            classified_count=len(final_results),
            inserted_count=inserted_count,
            max_concurrency=actual_concurrency,
            llm_count=llm_count,
            rule_count=0,
            failed_llm_batches=failed_llm_batches,
            distribution=dict(distribution),
            status_distribution=dict(status_distribution),
        )
        finish_run(
            config.database_path,
            run_id,
            raw_count=len(messages),
            stored_count=inserted_count,
            metadata=run_metadata | result.model_dump(),
        )
        return result
    except Exception as exc:
        fail_run(config.database_path, run_id, exc)
        raise
    finally:
        conn.close()


def classify_batch_with_llm(
    config: RadarConfig,
    batch: list[RawMessage],
    provider_name: str | None,
) -> list[MessageClassification]:
    """调用 LLM 批量分类；调用方负责失败回退。"""

    now = datetime.now()
    selected_provider, _ = resolve_provider(config, provider_name=provider_name, task=CLASSIFY_TASK)
    items = chat_json_list(
        config,
        _prompt_messages(batch),
        provider_name=selected_provider,
        disable_thinking=True,
    )
    return _normalize_llm_items(batch, items, now=now, llm_provider=selected_provider)


def _classify_with_llm(
    conn: Connection,
    config: RadarConfig,
    messages: list[RawMessage],
    *,
    provider_name: str | None,
    provider_names: list[str] | None,
    batch_size: int,
    max_concurrency: int | None,
    llm_batch_classifier: ClassifyBatchFn,
) -> tuple[list[MessageClassification], int, int, int, int]:
    results_by_id = {
        message.message_id: _unknown_classification(message, reason="LLM 未返回结果")
        for message in messages
    }
    inserted_count = 0
    llm_count = 0
    failed_batches = 0
    batches = _batches(messages, batch_size)
    provider_pool = _provider_pool(config, provider_name=provider_name, provider_names=provider_names)
    concurrency = max_concurrency or CLASSIFY_MAX_CONCURRENCY

    def worker(index: int, batch: list[RawMessage]) -> list[MessageClassification]:
        return llm_batch_classifier(config, batch, provider_pool[index % len(provider_pool)])

    def on_result(
        _index: int,
        batch: list[RawMessage],
        llm_results: list[MessageClassification],
    ) -> None:
        nonlocal inserted_count, llm_count, failed_batches
        batch_results, batch_llm_count, batch_failed = _normalize_batch_results(llm_results, batch)
        inserted_count += upsert_message_classifications(conn, batch_results)
        llm_count += batch_llm_count
        failed_batches += batch_failed
        for item in batch_results:
            results_by_id[item.message_id] = item

    def on_error(_index: int, batch: list[RawMessage], _error: BaseException) -> None:
        nonlocal inserted_count, failed_batches
        batch_results = [_unknown_classification(message, reason="LLM 批次失败") for message in batch]
        inserted_count += upsert_message_classifications(conn, batch_results)
        failed_batches += 1
        for item in batch_results:
            results_by_id[item.message_id] = item

    stats = run_work_pool(
        batches,
        max_workers=concurrency,
        worker=worker,
        on_result=on_result,
        on_error=on_error,
    )
    return (
        [results_by_id[message.message_id] for message in messages],
        inserted_count,
        llm_count,
        failed_batches,
        stats.actual_workers,
    )


def _normalize_batch_results(
    llm_results: list[MessageClassification],
    batch: list[RawMessage],
) -> tuple[list[MessageClassification], int, int]:
    batch_ids = {message.message_id for message in batch}
    messages_by_id = {message.message_id: message for message in batch}
    results: list[MessageClassification] = []
    seen_ids: set[str] = set()
    for item in llm_results:
        if item.message_id not in batch_ids or item.message_id in seen_ids:
            continue
        results.append(item)
        seen_ids.add(item.message_id)

    failed_batches = 0
    for missing_id in batch_ids - seen_ids:
        results.append(_unknown_classification(messages_by_id[missing_id], reason="LLM 未返回结果"))
        failed_batches = 1
    return results, len(seen_ids), failed_batches


def _prompt_messages(batch: list[RawMessage]) -> list[dict[str, str]]:
    lines = []
    for index, message in enumerate(batch, 1):
        group = message.group_name or ""
        content = message.raw_content[:MAX_LLM_CONTENT_CHARS]
        lines.append(
            f"[{index}] 来源: {message.source}; 群名: {group}; 发送人: {message.sender}\n{content}"
        )
    return [
        {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
        {"role": "user", "content": "以下是待分类消息：\n\n" + "\n\n".join(lines)},
    ]


def _normalize_llm_items(
    batch: list[RawMessage],
    items: list[dict[str, object]],
    *,
    now: datetime,
    llm_provider: str | None,
) -> list[MessageClassification]:
    messages_by_index = {index: message for index, message in enumerate(batch, 1)}
    results: list[MessageClassification] = []
    for item in items:
        index = _as_int(item.get("index"))
        if index is None or index not in messages_by_index:
            continue
        message = messages_by_index[index]
        category = _as_category(item.get("category"))
        confidence = _as_confidence(item.get("confidence"))
        results.append(
            MessageClassification(
                message_id=message.message_id,
                category=category,
                confidence=confidence,
                reason=str(item.get("reason") or "LLM 分类"),
                status=_status_for(category, confidence),
                classifier_type="llm",
                llm_provider=llm_provider,
                prompt_version=CLASSIFY_PROMPT_VERSION,
                classifier_version=CLASSIFIER_VERSION,
                created_at=now,
                updated_at=now,
            )
        )
    return results


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _as_category(value: object) -> MessageCategory:
    text = str(value or "unknown")
    return text if text in _CATEGORIES else "unknown"


def _as_confidence(value: object) -> float:
    try:
        confidence = float(str(value))
    except (TypeError, ValueError):
        return 0.5
    return min(max(confidence, 0.0), 1.0)


def _status_for(category: MessageCategory, confidence: float) -> ClassificationStatus:
    if category in {"chat", "tool_ad"}:
        return "ignored"
    if confidence >= NEEDS_REVIEW_THRESHOLD:
        return "auto"
    return "needs_review"


def _batches(messages: list[RawMessage], batch_size: int) -> list[list[RawMessage]]:
    return [messages[i : i + batch_size] for i in range(0, len(messages), batch_size)]


def _provider_pool(
    config: RadarConfig,
    *,
    provider_name: str | None,
    provider_names: list[str] | None,
) -> list[str | None]:
    if provider_names:
        return provider_names
    if provider_name:
        return [provider_name]
    selected_name, _ = resolve_provider(config, task=CLASSIFY_TASK)
    return [selected_name]


def _unknown_classification(message: RawMessage, *, reason: str) -> MessageClassification:
    now = datetime.now()
    return MessageClassification(
        message_id=message.message_id,
        category="unknown",
        confidence=0.0,
        reason=reason,
        status="needs_review",
        classifier_type="llm",
        classifier_version=CLASSIFIER_VERSION,
        created_at=now,
        updated_at=now,
    )


def _run_target(
    source: MessageSource | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> str:
    parts = [source or "all"]
    if start_time:
        parts.append(start_time.isoformat())
    if end_time:
        parts.append(end_time.isoformat())
    return "|".join(parts)
