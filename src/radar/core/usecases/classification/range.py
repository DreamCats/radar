from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.models import ClassificationRetryMode, MessageSource
from radar.core.storage import fail_run, finish_run, start_run, update_run_progress
from radar.core.storage import connect, init_db, list_messages_for_classification
from radar.core.usecases.classification.messages import (
    CLASSIFY_BATCH_SIZE,
    CLASSIFY_MAX_CONCURRENCY,
    NEEDS_REVIEW_THRESHOLD,
    ClassifyBatchFn,
    classify_batch_with_llm,
    _classify_candidates,
)
from radar.core.usecases.time_windows import time_chunks


class ClassifyRangeResult(BaseModel):
    run_id: str
    source: MessageSource | None = None
    start_time: datetime
    end_time: datetime
    chunk_count: int = 0
    empty_chunk_count: int = 0
    scanned_count: int = 0
    classified_count: int = 0
    inserted_count: int = 0
    max_concurrency: int = 0
    llm_count: int = 0
    rule_count: int = 0
    failed_llm_batches: int = 0
    distribution: dict[str, int] = Field(default_factory=dict)
    status_distribution: dict[str, int] = Field(default_factory=dict)


def classify_messages_range(
    config: RadarConfig,
    *,
    source: MessageSource | None = None,
    start_time: datetime,
    end_time: datetime,
    chunk_hours: int = 1,
    limit: int = 500,
    force: bool = False,
    use_llm: bool = True,
    provider_name: str | None = None,
    provider_names: list[str] | None = None,
    batch_size: int = CLASSIFY_BATCH_SIZE,
    max_concurrency: int | None = None,
    retry: ClassificationRetryMode | None = None,
    low_confidence_threshold: float = NEEDS_REVIEW_THRESHOLD,
    llm_batch_classifier: ClassifyBatchFn | None = None,
    run_id: str | None = None,
) -> ClassifyRangeResult:
    """按时间窗口分类消息；写入以 message_id 幂等，窗口内用游标翻完。"""

    _validate_range(
        start_time,
        end_time,
        chunk_hours,
        limit,
        batch_size,
        max_concurrency,
        low_confidence_threshold,
    )
    run_metadata = {
        "source": source,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "chunk_hours": chunk_hours,
        "limit": limit,
        "force": force,
        "use_llm": use_llm,
        "provider_name": provider_name,
        "provider_names": provider_names,
        "batch_size": batch_size,
        "max_concurrency": max_concurrency or CLASSIFY_MAX_CONCURRENCY,
        "retry": retry,
        "low_confidence_threshold": low_confidence_threshold,
    }
    if run_id is None:
        run_id = start_run(
            config.database_path,
            kind="message_classify_range",
            target=_run_target(source, start_time, end_time),
            metadata=run_metadata,
        )

    conn = connect(config.database_path)
    try:
        init_db(conn)
        chunks = time_chunks(start_time, end_time, timedelta(hours=chunk_hours))
        distribution: Counter[str] = Counter()
        status_distribution: Counter[str] = Counter()
        scanned_count = 0
        classified_count = 0
        inserted_count = 0
        llm_count = 0
        failed_llm_batches = 0
        empty_chunk_count = 0
        actual_max_concurrency = 0
        classifier = llm_batch_classifier or classify_batch_with_llm

        update_run_progress(
            config.database_path,
            run_id,
            metadata={
                "stage": "准备分类",
                "chunk_count": len(chunks),
                "completed_chunk_count": 0,
                "empty_chunk_count": 0,
                "scanned_count": 0,
                "classified_count": 0,
                "inserted_count": 0,
                "llm_count": 0,
                "failed_llm_batches": 0,
            },
        )

        for chunk_index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            chunk_scanned = 0
            cursor_time: str | None = None
            cursor_id: str | None = None
            while True:
                messages = list_messages_for_classification(
                    conn,
                    source=source,
                    start_time=chunk_start.isoformat(),
                    end_time=chunk_end.isoformat(),
                    end_inclusive=False,
                    cursor_time=cursor_time,
                    cursor_id=cursor_id,
                    limit=limit,
                    force=force,
                    retry=retry,
                    low_confidence_threshold=low_confidence_threshold,
                )
                if not messages:
                    break

                results, inserted, llm, failed_batches, actual_concurrency = _classify_candidates(
                    conn,
                    config,
                    messages,
                    use_llm=use_llm,
                    provider_name=provider_name,
                    provider_names=provider_names,
                    batch_size=batch_size,
                    max_concurrency=max_concurrency,
                    llm_batch_classifier=classifier,
                )
                scanned_count += len(messages)
                chunk_scanned += len(messages)
                classified_count += len(results)
                inserted_count += inserted
                llm_count += llm
                failed_llm_batches += failed_batches
                actual_max_concurrency = max(actual_max_concurrency, actual_concurrency)
                distribution.update(item.category for item in results)
                status_distribution.update(item.status for item in results)
                update_run_progress(
                    config.database_path,
                    run_id,
                    raw_count=scanned_count,
                    stored_count=inserted_count,
                    metadata={
                        "stage": "LLM 分类中",
                        "chunk_count": len(chunks),
                        "completed_chunk_count": chunk_index - 1,
                        "current_chunk_index": chunk_index,
                        "current_chunk_start": chunk_start.isoformat(),
                        "current_chunk_end": chunk_end.isoformat(),
                        "scanned_count": scanned_count,
                        "classified_count": classified_count,
                        "inserted_count": inserted_count,
                        "llm_count": llm_count,
                        "failed_llm_batches": failed_llm_batches,
                        "max_concurrency": actual_max_concurrency,
                        "distribution": dict(distribution),
                        "status_distribution": dict(status_distribution),
                    },
                )

                last_message = messages[-1]
                cursor_time = last_message.message_time.isoformat()
                cursor_id = last_message.message_id
                if len(messages) < limit:
                    break

            if chunk_scanned == 0:
                empty_chunk_count += 1
            update_run_progress(
                config.database_path,
                run_id,
                raw_count=scanned_count,
                stored_count=inserted_count,
                metadata={
                    "stage": "LLM 分类中",
                    "chunk_count": len(chunks),
                    "completed_chunk_count": chunk_index,
                    "current_chunk_index": chunk_index,
                    "current_chunk_start": chunk_start.isoformat(),
                    "current_chunk_end": chunk_end.isoformat(),
                    "empty_chunk_count": empty_chunk_count,
                    "scanned_count": scanned_count,
                    "classified_count": classified_count,
                    "inserted_count": inserted_count,
                    "llm_count": llm_count,
                    "failed_llm_batches": failed_llm_batches,
                    "max_concurrency": actual_max_concurrency,
                    "distribution": dict(distribution),
                    "status_distribution": dict(status_distribution),
                },
            )

        result = ClassifyRangeResult(
            run_id=run_id,
            source=source,
            start_time=start_time,
            end_time=end_time,
            chunk_count=len(chunks),
            empty_chunk_count=empty_chunk_count,
            scanned_count=scanned_count,
            classified_count=classified_count,
            inserted_count=inserted_count,
            max_concurrency=actual_max_concurrency,
            llm_count=llm_count,
            rule_count=0,
            failed_llm_batches=failed_llm_batches,
            distribution=dict(distribution),
            status_distribution=dict(status_distribution),
        )
        finish_run(
            config.database_path,
            run_id,
            status="skipped" if scanned_count == 0 else "succeeded",
            raw_count=scanned_count,
            stored_count=inserted_count,
            metadata=run_metadata | result.model_dump(),
        )
        return result
    except Exception as exc:
        fail_run(config.database_path, run_id, exc)
        raise
    finally:
        conn.close()


def _validate_range(
    start_time: datetime,
    end_time: datetime,
    chunk_hours: int,
    limit: int,
    batch_size: int,
    max_concurrency: int | None,
    low_confidence_threshold: float,
) -> None:
    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if chunk_hours < 1:
        raise ValueError("chunk_hours 必须大于 0")
    if limit < 1:
        raise ValueError("limit 必须大于 0")
    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    if max_concurrency is not None and max_concurrency < 1:
        raise ValueError("max_concurrency 必须大于 0")
    if low_confidence_threshold < 0 or low_confidence_threshold > 1:
        raise ValueError("low_confidence_threshold 必须在 0 到 1 之间")


def _run_target(
    source: MessageSource | None,
    start_time: datetime,
    end_time: datetime,
) -> str:
    return f"{source or 'all'}:{start_time.isoformat()}..{end_time.isoformat()}"
