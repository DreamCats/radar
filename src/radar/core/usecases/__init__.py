"""Core use cases that orchestrate lower-level capabilities."""

from radar.core.usecases.ingest_wechat import (
    IngestRangeResult,
    IngestWindowResult,
    ingest_wechat_range,
    ingest_wechat_window,
)

__all__ = [
    "IngestRangeResult",
    "IngestWindowResult",
    "ingest_wechat_range",
    "ingest_wechat_window",
]
