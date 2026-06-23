from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from radar.core.chat.tools import ChatTool
from radar.core.config import RadarConfig
from radar.core.messages import CatalystFeedFilters, CatalystFeedItem, load_catalyst_terms, list_catalyst_feed
from radar.core.models import MessageSource
from radar.core.storage import connect, init_db
from radar.core.usecases.catalyst_stocks import load_catalyst_stock_detector

_SOURCE_MAP: dict[str, MessageSource | None] = {
    "all": None,
    "个人消息": "个人消息",
    "个人群": "个人群",
}


class RadarCatalystTools:
    """Catalyst clue tools for chat agent evidence scanning."""

    def __init__(self, config: RadarConfig):
        self.config = config

    def tools(self) -> list[ChatTool]:
        return [self.scan_catalysts_tool(), self.list_catalyst_terms_tool()]

    def scan_catalysts_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_scan_catalysts",
            description=(
                "按催化词词库扫描本地微信消息，复用催化词页的白名单命中、去重、标签计数和标的识别逻辑。"
                "适合查最近或指定时间窗口内的催化线索。"
            ),
            input_schema=_object_schema(
                {
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "source": {"type": "string", "enum": ["all", "个人消息", "个人群"]},
                    "group_name": {"type": "string"},
                    "category_ids": {"type": "array", "items": {"type": "string"}},
                    "keyword": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 80},
                    "cursor_time": {"type": "string"},
                    "cursor_key": {"type": "string"},
                }
            ),
            handler=self.scan_catalysts,
        )

    def list_catalyst_terms_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_list_catalyst_terms",
            description="只读当前催化词词库，返回标签、颜色和关键词；不修改配置。",
            input_schema=_object_schema({}),
            handler=self.list_catalyst_terms,
        )

    def scan_catalysts(self, args: dict[str, Any]) -> dict[str, Any]:
        end_time = _optional_datetime(args.get("end_time")) or datetime.now()
        start_time = _optional_datetime(args.get("start_time")) or (end_time - timedelta(days=2))
        filters = CatalystFeedFilters(
            start_time=start_time,
            end_time=end_time,
            source=_source_value(args.get("source")),
            group_name=_optional_str(args.get("group_name")),
            category_ids=_string_list(args.get("category_ids")),
            keyword=_optional_str(args.get("keyword")),
            dedupe=True,
            cursor_time=_optional_datetime(args.get("cursor_time")),
            cursor_key=_optional_str(args.get("cursor_key")),
            limit=_bounded_int(args.get("limit"), default=20, maximum=80),
        )
        conn = connect(self.config.database_path)
        try:
            init_db(conn)
            page = list_catalyst_feed(
                conn,
                load_catalyst_terms(self.config),
                filters,
                stock_detector=load_catalyst_stock_detector(self.config),
            )
        finally:
            conn.close()
        return {
            "window": {"start_time": start_time.isoformat(), "end_time": end_time.isoformat()},
            "summary": page.summary.model_dump(mode="json"),
            "items": [_item_summary(item) for item in page.items],
            "next_cursor_time": _json_value(page.next_cursor_time),
            "next_cursor_key": page.next_cursor_key,
        }

    def list_catalyst_terms(self, args: dict[str, Any]) -> dict[str, Any]:
        library = load_catalyst_terms(self.config)
        return library.model_dump(mode="json")


def _item_summary(item: CatalystFeedItem) -> dict[str, Any]:
    return {
        "key": item.key,
        "message_id": item.message_id,
        "source": item.source,
        "sender": item.sender,
        "group_name": item.group_name,
        "first_message_time": item.first_message_time.isoformat(),
        "latest_message_time": item.latest_message_time.isoformat(),
        "content": _clip(item.raw_content, 700),
        "content_length": len(item.raw_content),
        "content_truncated": len(item.raw_content) > 700,
        "matched_terms": [hit.model_dump(mode="json") for hit in item.matched_terms],
        "stock_mentions": [stock.model_dump(mode="json") for stock in item.stock_mentions],
        "duplicate_count": item.duplicate_count,
        "duplicate_sources": [
            {
                "message_id": source.message_id,
                "source": source.source,
                "sender": source.sender,
                "group_name": source.group_name,
                "message_time": source.message_time.isoformat(),
            }
            for source in item.duplicate_sources[:8]
        ],
    }


def _object_schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _bounded_int(value: object, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    if parsed < 1:
        return default
    return min(parsed, maximum)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_datetime(value: object) -> datetime | None:
    text = _optional_str(value)
    if text is None:
        return None
    return datetime.fromisoformat(text)


def _source_value(value: object) -> MessageSource | None:
    text = str(value or "all")
    if text not in _SOURCE_MAP:
        raise ValueError("source 必须是 all、个人消息 或 个人群")
    return _SOURCE_MAP[text]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
