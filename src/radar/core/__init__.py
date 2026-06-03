"""Shared core used by CLI and Web server."""

from radar.core.config import RadarConfig
from radar.core.llm import LlmConfigError, chat, chat_json, chat_json_list
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
    "LlmConfigError",
    "chat",
    "chat_json",
    "chat_json_list",
    "connect",
    "ingest_wechat_range",
    "ingest_wechat_window",
    "init_db",
    "list_messages",
    "upsert_messages",
]
