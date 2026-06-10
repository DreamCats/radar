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
from radar.core.tushare import resolve_stock
from radar.core.usecases.stock_evidence_chain import get_stock_evidence_stock_chart, latest_stock_evidence_chain


class RadarBuiltinExtension:
    """Radar 内置只读工具，给 chat agent 提供受控的项目数据读取能力。"""

    name = "radar_builtin"

    def __init__(self, config: RadarConfig):
        self.config = config

    def register(self, context: ExtensionContext) -> None:
        for tool in (
            self._search_messages_tool(),
            self._get_conversation_window_tool(),
            self._list_conversations_tool(),
            self._get_message_context_tool(),
            self._message_overview_tool(),
            *RadarTushareTools(self.config).tools(),
            self._stock_evidence_chart_tool(),
            self._stock_evidence_chain_tool(),
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

    def _get_conversation_window_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_conversation_window",
            description="按群聊或个人私聊读取一个时间窗口内的完整消息，用于理解当前会话上下文并支持向前翻页。",
            input_schema=_object_schema(
                {
                    "source": {"type": "string", "enum": ["个人消息", "个人群"]},
                    "group_name": {"type": "string"},
                    "sender": {"type": "string"},
                    "conversation": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "cursor_time": {"type": "string"},
                    "cursor_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 80},
                },
                required=["source"],
            ),
            handler=self._get_conversation_window,
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
            description="读取本地消息库总览、来源分布、热门群和小时分布。",
            input_schema=_object_schema(
                {
                    "days": {"type": "integer", "minimum": 1, "maximum": 60},
                    "top_limit": {"type": "integer", "minimum": 1, "maximum": 20},
                }
            ),
            handler=self._message_overview,
        )

    def _stock_evidence_chain_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_stock_evidence_chain",
            description="读取 radar 最新个股证据链判断；可按股票或阶段过滤，返回阶段、证据、风险和市场证据摘要。",
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "stage": {"type": "string", "enum": ["lead", "seed", "formed", "spreading", "pricing", "crowded"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 120},
                }
            ),
            handler=self._stock_evidence_chain,
        )

    def _stock_evidence_chart_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_stock_evidence_chart",
            description="读取个股证据链策略同源的本地日 K 线和成交额证据，返回 candles 及价格/成交额摘要。",
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 260},
                },
                required=["stock"],
            ),
            handler=self._stock_evidence_chart,
        )

    def _backtest_summary_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_backtest_summary",
            description="读取高质量证据事件回测汇总，按来源、分析师、股票或行业聚合。",
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

    def _get_conversation_window(self, args: dict[str, Any]) -> dict[str, Any]:
        source = str(args["source"])
        conversation = _optional_str(args.get("conversation"))
        group_name = _optional_str(args.get("group_name"))
        sender = _optional_str(args.get("sender"))
        if source == "个人群":
            group_name = group_name or conversation
            if not group_name:
                raise ValueError("读取个人群窗口需要 group_name 或 conversation")
        elif source == "个人消息":
            sender = sender or conversation
            if not sender:
                raise ValueError("读取个人消息窗口需要 sender 或 conversation")
        else:
            raise ValueError("source 必须是 个人群 或 个人消息")

        filters = MessageFilters.model_validate(
            {
                "source": source,
                "group_name": group_name if source == "个人群" else None,
                "sender": sender if source == "个人消息" else None,
                "start_time": _optional_datetime(args.get("start_time")),
                "end_time": _optional_datetime(args.get("end_time")),
                "cursor_time": _optional_datetime(args.get("cursor_time")),
                "cursor_id": _optional_str(args.get("cursor_id")),
                "limit": _bounded_int(args.get("limit"), default=50, maximum=80),
            }
        )
        conn = connect(self.config.database_path)
        try:
            init_db(conn)
            page = list_messages(conn, filters)
        finally:
            conn.close()
        return {
            "source": source,
            "group_name": group_name,
            "sender": sender,
            "items": [_message_window_item(item) for item in page.items],
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
            )
        finally:
            conn.close()
        return overview.model_dump(mode="json")

    def _stock_evidence_chain(self, args: dict[str, Any]) -> dict[str, Any]:
        stock = _optional_str(args.get("stock"))
        stage = _optional_str(args.get("stage"))
        limit = _bounded_int(args.get("limit"), default=20, maximum=120)
        dashboard = latest_stock_evidence_chain(self.config, limit=500 if stock else limit)
        items = dashboard.items
        if stock:
            stock_key = stock.upper()
            items = [
                item
                for item in items
                if stock_key in item.ts_code.upper() or stock in item.stock_name
            ]
        if stage:
            items = [item for item in items if item.stage == stage]
        limited_items = items[:limit]
        dashboard = dashboard.model_copy(update={"items": limited_items, "item_count": len(limited_items), "stage_counts": _stock_stage_counts(limited_items)})
        return dashboard.model_dump(mode="json")

    def _stock_evidence_chart(self, args: dict[str, Any]) -> dict[str, Any]:
        stock = str(args["stock"]).strip()
        ts_code = resolve_stock(self.config, stock)
        chart = get_stock_evidence_stock_chart(
            self.config,
            ts_code=ts_code,
            days=_bounded_int(args.get("days"), default=120, maximum=260),
        )
        result = chart.model_dump(mode="json")
        result.update(
            {
                "found": bool(chart.candles),
                "stock": stock,
                "summary": _stock_chart_summary(chart.candles),
            }
        )
        return result

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


def _stock_stage_counts(items: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        stage = str(getattr(item, "stage", "") or "")
        if stage:
            counts[stage] = counts.get(stage, 0) + 1
    return counts


def _stock_chart_summary(candles: list[Any]) -> dict[str, Any]:
    if not candles:
        return {}

    first = candles[0]
    latest = candles[-1]
    high_close = max(candles, key=lambda item: item.close)
    low_close = min(candles, key=lambda item: item.close)
    latest_amount = getattr(latest, "amount", None)
    avg5_amount = _average_amount(candles[-5:])
    avg20_amount = _average_amount(candles[-20:])
    return {
        "first_trade_date": first.trade_date,
        "latest_trade_date": latest.trade_date,
        "latest_close": latest.close,
        "latest_pct_chg": getattr(latest, "pct_chg", None),
        "return_from_first": _rate(latest.close, first.close),
        "return_from_low_close": _rate(latest.close, low_close.close),
        "drawdown_from_high_close": _rate(latest.close, high_close.close),
        "high_close_trade_date": high_close.trade_date,
        "high_close": high_close.close,
        "low_close_trade_date": low_close.trade_date,
        "low_close": low_close.close,
        "latest_amount": latest_amount,
        "avg5_amount": avg5_amount,
        "avg20_amount": avg20_amount,
        "latest_amount_vs_avg20": _rate(latest_amount, avg20_amount),
    }


def _average_amount(candles: list[Any]) -> float | None:
    values = [float(item.amount) for item in candles if getattr(item, "amount", None) is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _rate(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0:
        return None
    return round((current - base) / base, 4)


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


def _message_window_item(message: RawMessage) -> dict[str, Any]:
    content = _clip(message.raw_content, 2000)
    return {
        "message_id": message.message_id,
        "source": message.source,
        "sender": message.sender,
        "group_name": message.group_name,
        "message_time": message.message_time.isoformat(),
        "content": content,
        "content_length": len(message.raw_content),
        "content_truncated": content != message.raw_content,
    }


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
