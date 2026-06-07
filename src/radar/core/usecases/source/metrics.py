from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from radar.core.usecases.source.models import SourceStructure


class SourceExtractResult(BaseModel):
    run_id: str
    scanned_count: int = 0
    extracted_count: int = 0
    inserted_count: int = 0
    llm_count: int = 0
    failed_llm_batches: int = 0
    max_concurrency: int = 0
    provider_pool: list[str | None] = Field(default_factory=list)
    llm_batch_metrics: list["SourceExtractBatchMetric"] = Field(default_factory=list)
    failed_llm_batch_details: list["SourceExtractBatchMetric"] = Field(default_factory=list)
    provider_stats: list["SourceExtractProviderStats"] = Field(default_factory=list)


class SourceExtractBatchMetric(BaseModel):
    batch_index: int
    provider: str | None = None
    message_count: int = 0
    result_count: int = 0
    elapsed_ms: int = 0
    status: str
    error_type: str | None = None
    error_message: str | None = None


class SourceExtractProviderStats(BaseModel):
    provider: str | None = None
    batch_count: int = 0
    failed_count: int = 0
    message_count: int = 0
    result_count: int = 0
    total_elapsed_ms: int = 0
    max_elapsed_ms: int = 0
    avg_elapsed_ms: int = 0


@dataclass(frozen=True)
class TimedBatchResult:
    items: list[SourceStructure]
    elapsed_ms: int


class SourceExtractBatchError(RuntimeError):
    def __init__(self, *, provider: str | None, elapsed_ms: int, original: BaseException) -> None:
        super().__init__(str(original))
        self.provider = provider
        self.elapsed_ms = elapsed_ms
        self.original = original


def provider_for_batch(provider_pool: list[str | None], batch_index: int) -> str | None:
    return provider_pool[batch_index % len(provider_pool)] if provider_pool else None


def provider_stats(batch_metrics: list[SourceExtractBatchMetric]) -> list[SourceExtractProviderStats]:
    grouped: dict[str | None, list[SourceExtractBatchMetric]] = {}
    for metric in batch_metrics:
        grouped.setdefault(metric.provider, []).append(metric)

    stats: list[SourceExtractProviderStats] = []
    for provider, metrics in grouped.items():
        total_elapsed = sum(item.elapsed_ms for item in metrics)
        stats.append(
            SourceExtractProviderStats(
                provider=provider,
                batch_count=len(metrics),
                failed_count=sum(1 for item in metrics if item.status == "failed"),
                message_count=sum(item.message_count for item in metrics),
                result_count=sum(item.result_count for item in metrics),
                total_elapsed_ms=total_elapsed,
                max_elapsed_ms=max((item.elapsed_ms for item in metrics), default=0),
                avg_elapsed_ms=round(total_elapsed / len(metrics)) if metrics else 0,
            )
        )
    stats.sort(key=lambda item: (item.failed_count, item.avg_elapsed_ms), reverse=True)
    return stats
