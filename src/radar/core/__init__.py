"""Shared core used by CLI and Web server."""

from radar.core.config import RadarConfig
from radar.core.models import MessageSource, RawMessage
from radar.core.query import MessageFilters, MessagePage, list_messages
from radar.core.store import connect, init_db, upsert_messages
from radar.core.usecases import (
    IngestRangeResult,
    IngestWindowResult,
    ingest_wechat_range,
    ingest_wechat_window,
)

__all__ = [
    "MessageFilters",
    "MessagePage",
    "MessageSource",
    "RadarConfig",
    "RawMessage",
    "IngestRangeResult",
    "IngestWindowResult",
    "connect",
    "ingest_wechat_range",
    "ingest_wechat_window",
    "init_db",
    "list_messages",
    "upsert_messages",
]
