from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from radar.core.algorithms.anchors import AnchorRankingConfig, rank_anchor_batch
from radar.core.config import RadarConfig
from radar.core.models import MessageAnchor, MessageAnchorType, MessageCategory, MessageSource
from radar.core.runs import fail_run, finish_run, start_run, update_run_progress
from radar.core.store import connect, init_db, list_messages_for_anchoring, replace_message_anchors
from radar.core.usecases.anchoring.dictionary import load_anchor_dictionary
from radar.core.usecases.anchoring.extractor import (
    ANCHOR_EXTRACTOR_VERSION,
    Segmenter,
    extract_message_anchors,
)
from radar.core.usecases.time_windows import time_chunks

DEFAULT_ANCHOR_CATEGORIES: list[MessageCategory] = ["research", "recommendation", "industry"]


class AnchorRangeResult(BaseModel):
    run_id: str
    source: MessageSource | None = None
    category: MessageCategory | None = None
    categories: list[MessageCategory] = Field(default_factory=list)
    min_classification_confidence: float | None = None
    trade_date: str
    start_time: datetime
    end_time: datetime
    chunk_count: int = 0
    empty_chunk_count: int = 0
    scanned_count: int = 0
    anchored_message_count: int = 0
    anchor_count: int = 0
    dictionary_anchor_count: int = 0
    extractor_version: str = ANCHOR_EXTRACTOR_VERSION
    type_distribution: dict[MessageAnchorType, int] = Field(default_factory=dict)
    top_anchors: dict[str, int] = Field(default_factory=dict)


def anchor_messages_range(
    config: RadarConfig,
    *,
    trade_date: str,
    source: MessageSource | None = None,
    category: MessageCategory | None = None,
    categories: list[MessageCategory] | None = None,
    min_classification_confidence: float | None = None,
    start_time: datetime,
    end_time: datetime,
    chunk_hours: int = 1,
    limit: int = 500,
    force: bool = False,
    max_anchors_per_message: int = 7,
    extractor_version: str = ANCHOR_EXTRACTOR_VERSION,
    segmenter: Segmenter | None = None,
    run_id: str | None = None,
) -> AnchorRangeResult:
    """按时间窗口抽取消息市场 anchor；本地词库命中，暂不调用 LLM。"""

    _validate_range(
        start_time,
        end_time,
        chunk_hours,
        limit,
        max_anchors_per_message,
        min_classification_confidence,
    )
    category_values = _normalize_categories(category, categories)
    dictionary = load_anchor_dictionary(config, trade_date=trade_date)
    if dictionary.anchor_count == 0:
        raise ValueError(f"未找到 {trade_date} 的 anchor 词库，请先刷新 market anchors")

    run_metadata = {
        "source": source,
        "categories": category_values,
        "min_classification_confidence": min_classification_confidence,
        "trade_date": trade_date,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "chunk_hours": chunk_hours,
        "limit": limit,
        "force": force,
        "max_anchors_per_message": max_anchors_per_message,
        "extractor_version": extractor_version,
        "dictionary_anchor_count": dictionary.anchor_count,
    }
    if run_id is None:
        run_id = start_run(
            config.database_path,
            kind="message_anchor_range",
            target=_run_target(source, category_values, start_time, end_time),
            metadata=run_metadata,
        )

    conn = connect(config.database_path)
    try:
        init_db(conn)
        chunks = time_chunks(start_time, end_time, timedelta(hours=chunk_hours))
        empty_chunk_count = 0
        scanned_count = 0
        anchored_message_count = 0
        anchor_count = 0
        type_distribution: Counter[MessageAnchorType] = Counter()
        top_anchors: Counter[str] = Counter()

        update_run_progress(
            config.database_path,
            run_id,
            metadata={
                "stage": "准备抽取 anchor",
                "chunk_count": len(chunks),
                "completed_chunk_count": 0,
                "dictionary_anchor_count": dictionary.anchor_count,
            },
        )

        for chunk_index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            chunk_scanned = 0
            cursor_time: str | None = None
            cursor_id: str | None = None
            while True:
                messages = list_messages_for_anchoring(
                    conn,
                    source=source,
                    categories=category_values,
                    min_classification_confidence=min_classification_confidence,
                    start_time=chunk_start.isoformat(),
                    end_time=chunk_end.isoformat(),
                    end_inclusive=False,
                    cursor_time=cursor_time,
                    cursor_id=cursor_id,
                    limit=limit,
                    force=force,
                    extractor_version=extractor_version,
                )
                if not messages:
                    break

                candidates_by_message: dict[str, list[MessageAnchor]] = {}
                for message in messages:
                    candidates_by_message[message.message_id] = extract_message_anchors(
                        message,
                        dictionary,
                        segmenter=segmenter,
                        extractor_version=extractor_version,
                        max_anchors=max(max_anchors_per_message * 4, 24),
                    )

                ranked_by_message = rank_anchor_batch(
                    candidates_by_message,
                    config=AnchorRankingConfig(max_anchors_per_message=max_anchors_per_message),
                )
                batch_anchors = [
                    item
                    for message in messages
                    for item in ranked_by_message.get(message.message_id, [])
                ]
                for items in ranked_by_message.values():
                    if items:
                        anchored_message_count += 1

                inserted = replace_message_anchors(
                    conn,
                    message_ids=[message.message_id for message in messages],
                    anchors=batch_anchors,
                    trade_date=trade_date,
                    extractor_version=extractor_version,
                )
                scanned_count += len(messages)
                chunk_scanned += len(messages)
                anchor_count += inserted
                type_distribution.update(item.anchor_type for item in batch_anchors)
                top_anchors.update(item.name for item in batch_anchors)
                update_run_progress(
                    config.database_path,
                    run_id,
                    raw_count=scanned_count,
                    stored_count=anchor_count,
                    metadata={
                        "stage": "抽取 anchor",
                        "chunk_count": len(chunks),
                        "completed_chunk_count": chunk_index - 1,
                        "current_chunk_index": chunk_index,
                        "current_chunk_start": chunk_start.isoformat(),
                        "current_chunk_end": chunk_end.isoformat(),
                        "scanned_count": scanned_count,
                        "anchored_message_count": anchored_message_count,
                        "anchor_count": anchor_count,
                        "type_distribution": dict(type_distribution),
                        "top_anchors": dict(top_anchors.most_common(20)),
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
                stored_count=anchor_count,
                metadata={
                    "stage": "抽取 anchor",
                    "chunk_count": len(chunks),
                    "completed_chunk_count": chunk_index,
                    "current_chunk_index": chunk_index,
                    "empty_chunk_count": empty_chunk_count,
                    "scanned_count": scanned_count,
                    "anchored_message_count": anchored_message_count,
                    "anchor_count": anchor_count,
                },
            )

        result = AnchorRangeResult(
            run_id=run_id,
            source=source,
            category=category_values[0] if len(category_values) == 1 else None,
            categories=category_values,
            min_classification_confidence=min_classification_confidence,
            trade_date=trade_date,
            start_time=start_time,
            end_time=end_time,
            chunk_count=len(chunks),
            empty_chunk_count=empty_chunk_count,
            scanned_count=scanned_count,
            anchored_message_count=anchored_message_count,
            anchor_count=anchor_count,
            dictionary_anchor_count=dictionary.anchor_count,
            extractor_version=extractor_version,
            type_distribution=dict(type_distribution),
            top_anchors=dict(top_anchors.most_common(20)),
        )
        finish_run(
            config.database_path,
            run_id,
            status="skipped" if scanned_count == 0 else "succeeded",
            raw_count=scanned_count,
            stored_count=anchor_count,
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
    max_anchors_per_message: int,
    min_classification_confidence: float | None,
) -> None:
    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if chunk_hours < 1:
        raise ValueError("chunk_hours 必须大于 0")
    if limit < 1:
        raise ValueError("limit 必须大于 0")
    if max_anchors_per_message < 1:
        raise ValueError("max_anchors_per_message 必须大于 0")
    if min_classification_confidence is not None and not 0 <= min_classification_confidence <= 1:
        raise ValueError("min_classification_confidence 必须在 0 到 1 之间")


def _normalize_categories(
    category: MessageCategory | None,
    categories: list[MessageCategory] | None,
) -> list[MessageCategory]:
    values = list(categories or [])
    if category:
        values.append(category)
    if not values:
        values = DEFAULT_ANCHOR_CATEGORIES
    return list(dict.fromkeys(values))


def _run_target(
    source: MessageSource | None,
    categories: list[MessageCategory],
    start_time: datetime,
    end_time: datetime,
) -> str:
    category_text = ",".join(categories) if categories else "all"
    return f"{source or 'all'}:{category_text}:{start_time.isoformat()}..{end_time.isoformat()}"
