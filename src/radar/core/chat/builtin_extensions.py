from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from radar.core.chat.extensions import ExtensionContext
from radar.core.chat.shell_tool import build_shell_tool
from radar.core.chat.tushare_tools import RadarTushareTools
from radar.core.chat.tools import ChatTool
from radar.core.config import RadarConfig
from radar.core.messages import (
    ConversationFilters,
    MessageFilters,
    get_message_context,
    get_message_overview,
    list_conversations,
    list_messages,
)
from radar.core.models import RawMessage
from radar.core.store import connect, init_db
from radar.core.usecases.recommendation_backtest import DEFAULT_BACKTEST_WINDOWS, summarize_recommendation_backtests
from radar.core.usecases.source.storage import list_latest_source_signal_snapshots
from radar.core.usecases.strategy import build_strategy_dashboard


class RadarBuiltinExtension:
    """Radar 内置只读工具，给 chat agent 提供受控的项目数据读取能力。"""

    name = "radar_builtin"

    def __init__(self, config: RadarConfig):
        self.config = config

    def register(self, context: ExtensionContext) -> None:
        for tool in (
            self._search_messages_tool(),
            self._list_conversations_tool(),
            self._get_message_context_tool(),
            self._message_overview_tool(),
            *RadarTushareTools(self.config).tools(),
            self._strategy_dashboard_tool(),
            self._source_signals_tool(),
            self._backtest_summary_tool(),
        ):
            context.register_tool(tool)
        if self.config.chat.shell.enabled:
            context.register_tool(build_shell_tool(self.config))

    def _search_messages_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_search_messages",
            description="分页搜索 radar 本地微信消息，返回裁剪后的消息摘要和游标。",
            input_schema=_object_schema(
                {
                    "keyword": {"type": "string"},
                    "source": {"type": "string", "enum": ["个人消息", "个人群"]},
                    "group_name": {"type": "string"},
                    "sender": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                }
            ),
            handler=self._search_messages,
        )

    def _list_conversations_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_list_conversations",
            description="分页列出 radar 本地微信会话，按最近消息排序。",
            input_schema=_object_schema(
                {
                    "source": {"type": "string", "enum": ["个人消息", "个人群"]},
                    "keyword": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                }
            ),
            handler=self._list_conversations,
        )

    def _get_message_context_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_message_context",
            description="按 message_id 读取同一群或同一联系人的前后文。",
            input_schema=_object_schema(
                {
                    "message_id": {"type": "string"},
                    "radius": {"type": "integer", "minimum": 0, "maximum": 20},
                    "same_conversation": {"type": "boolean"},
                },
                required=["message_id"],
            ),
            handler=self._get_message_context,
        )

    def _message_overview_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_message_overview",
            description="读取本地消息库总览、来源分布、热门群和 anchor 热力。",
            input_schema=_object_schema(
                {
                    "days": {"type": "integer", "minimum": 1, "maximum": 60},
                    "top_limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    "anchor_limit": {"type": "integer", "minimum": 1, "maximum": 50},
                }
            ),
            handler=self._message_overview,
        )

    def _strategy_dashboard_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_strategy_dashboard",
            description="读取 radar 策略看板摘要，包括机会、源头质量和股票候选。",
            input_schema=_object_schema(
                {
                    "days": {"type": "integer", "minimum": 1, "maximum": 90},
                    "recent_days": {"type": "integer", "minimum": 1, "maximum": 30},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                }
            ),
            handler=self._strategy_dashboard,
        )

    def _source_signals_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_source_signals",
            description="读取最新或指定时间前的源头信号快照。",
            input_schema=_object_schema(
                {
                    "as_of_time": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                }
            ),
            handler=self._source_signals,
        )

    def _backtest_summary_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_backtest_summary",
            description="读取推荐事件回测汇总，按来源、分析师、股票或行业聚合。",
            input_schema=_object_schema(
                {
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "group_by": {
                        "type": "string",
                        "enum": ["source", "source_stock", "analyst", "analyst_stock", "sector", "analyst_sector", "stock"],
                    },
                    "windows": {"type": "array", "items": {"type": "integer"}},
                    "min_count": {"type": "integer", "minimum": 1, "maximum": 20},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                }
            ),
            handler=self._backtest_summary,
        )

    def _search_messages(self, args: dict[str, Any]) -> dict[str, Any]:
        filters = MessageFilters.model_validate(
            {
                "keyword": _optional_str(args.get("keyword")),
                "source": args.get("source"),
                "group_name": _optional_str(args.get("group_name")),
                "sender": _optional_str(args.get("sender")),
                "start_time": _optional_datetime(args.get("start_time")),
                "end_time": _optional_datetime(args.get("end_time")),
                "limit": _bounded_int(args.get("limit"), default=20, maximum=50),
            }
        )
        conn = connect(self.config.database_path)
        try:
            init_db(conn)
            page = list_messages(conn, filters)
        finally:
            conn.close()
        return {
            "items": [_message_summary(item) for item in page.items],
            "next_cursor_time": _json_value(page.next_cursor_time),
            "next_cursor_id": page.next_cursor_id,
        }

    def _list_conversations(self, args: dict[str, Any]) -> dict[str, Any]:
        filters = ConversationFilters.model_validate(
            {
                "source": args.get("source"),
                "keyword": _optional_str(args.get("keyword")),
                "start_time": _optional_datetime(args.get("start_time")),
                "end_time": _optional_datetime(args.get("end_time")),
                "limit": _bounded_int(args.get("limit"), default=20, maximum=50),
            }
        )
        conn = connect(self.config.database_path)
        try:
            init_db(conn)
            page = list_conversations(conn, filters)
        finally:
            conn.close()
        return page.model_dump(mode="json")

    def _get_message_context(self, args: dict[str, Any]) -> dict[str, Any]:
        conn = connect(self.config.database_path)
        try:
            init_db(conn)
            context = get_message_context(
                conn,
                message_id=str(args["message_id"]),
                radius=_bounded_int(args.get("radius"), default=5, maximum=20),
                same_conversation=bool(args.get("same_conversation", True)),
            )
        finally:
            conn.close()
        if context is None:
            return {"found": False, "message_id": str(args["message_id"])}
        return {
            "found": True,
            "target": _message_detail(context.target),
            "before": [_message_detail(item) for item in context.before],
            "after": [_message_detail(item) for item in context.after],
        }

    def _message_overview(self, args: dict[str, Any]) -> dict[str, Any]:
        conn = connect(self.config.database_path)
        try:
            init_db(conn)
            overview = get_message_overview(
                conn,
                days=_bounded_int(args.get("days"), default=14, maximum=60),
                top_limit=_bounded_int(args.get("top_limit"), default=8, maximum=20),
                anchor_limit=_bounded_int(args.get("anchor_limit"), default=20, maximum=50),
            )
        finally:
            conn.close()
        return overview.model_dump(mode="json")

    def _strategy_dashboard(self, args: dict[str, Any]) -> dict[str, Any]:
        dashboard = build_strategy_dashboard(
            self.config,
            days=_bounded_int(args.get("days"), default=30, maximum=90),
            recent_days=_bounded_int(args.get("recent_days"), default=7, maximum=30),
            limit=_bounded_int(args.get("limit"), default=8, maximum=20),
        )
        return dashboard.model_dump(mode="json")

    def _source_signals(self, args: dict[str, Any]) -> dict[str, Any]:
        conn = connect(self.config.database_path)
        try:
            init_db(conn)
            page = list_latest_source_signal_snapshots(
                conn,
                as_of_time=_optional_datetime(args.get("as_of_time")),
                limit=_bounded_int(args.get("limit"), default=10, maximum=50),
            )
        finally:
            conn.close()
        return page.model_dump(mode="json")

    def _backtest_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        end_time = _optional_datetime(args.get("end_time")) or datetime.now()
        start_time = _optional_datetime(args.get("start_time")) or (end_time - timedelta(days=30))
        windows = _windows(args.get("windows"))
        result = summarize_recommendation_backtests(
            self.config,
            start_time=start_time,
            end_time=end_time,
            group_by=str(args.get("group_by") or "analyst_sector"),  # type: ignore[arg-type]
            windows=windows,
            min_count=_bounded_int(args.get("min_count"), default=3, maximum=20),
            limit=_bounded_int(args.get("limit"), default=20, maximum=50),
        )
        return result.model_dump(mode="json")


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


def _windows(value: object) -> list[int]:
    if not isinstance(value, list):
        return list(DEFAULT_BACKTEST_WINDOWS)
    allowed = set(DEFAULT_BACKTEST_WINDOWS)
    parsed = sorted({int(item) for item in value if int(item) in allowed})
    return parsed or list(DEFAULT_BACKTEST_WINDOWS)


def _message_summary(message: RawMessage) -> dict[str, Any]:
    return {
        "message_id": message.message_id,
        "source": message.source,
        "sender": message.sender,
        "group_name": message.group_name,
        "message_time": message.message_time.isoformat(),
        "snippet": _clip(message.raw_content, 240),
    }


def _message_detail(message: RawMessage) -> dict[str, Any]:
    item = _message_summary(message)
    item["content"] = _clip(message.raw_content, 1000)
    return item


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
