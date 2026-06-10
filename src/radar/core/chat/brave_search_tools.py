from __future__ import annotations

from typing import Any

from radar.core.brave_search import search_context
from radar.core.chat.tools import ChatTool
from radar.core.config import RadarConfig


class RadarBraveSearchTools:
    def __init__(self, config: RadarConfig):
        self.config = config

    def tools(self) -> list[ChatTool]:
        return [self.search_web_tool()]

    def search_web_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_search_web",
            description=(
                "通过 Brave Search 搜索公网网页，返回适合回答问题的网页来源上下文。"
                "适合查询最新信息、官方文档、错误排查、新闻背景或需要外部证据的问题。"
            ),
            input_schema=_object_schema(
                {
                    "query": {"type": "string"},
                    "count": {"type": "integer", "minimum": 1, "maximum": 10},
                    "max_tokens": {"type": "integer", "minimum": 1024, "maximum": 8192},
                    "max_tokens_per_url": {
                        "type": "integer",
                        "minimum": 256,
                        "maximum": 4096,
                    },
                    "threshold": {
                        "type": "string",
                        "enum": ["strict", "balanced", "lenient"],
                    },
                    "include_sites": {"type": "array", "items": {"type": "string"}},
                    "exclude_sites": {"type": "array", "items": {"type": "string"}},
                },
                required=["query"],
            ),
            handler=self.search_web,
        )

    def search_web(self, args: dict[str, Any]) -> dict[str, Any]:
        result = search_context(
            self.config,
            str(args["query"]),
            count=_bounded_int(args.get("count"), default=5, minimum=1, maximum=10),
            max_tokens=_bounded_int(
                args.get("max_tokens"),
                default=4096,
                minimum=1024,
                maximum=8192,
            ),
            max_tokens_per_url=_optional_bounded_int(
                args.get("max_tokens_per_url"),
                minimum=256,
                maximum=4096,
            ),
            threshold=_optional_str(args.get("threshold")),
            include_sites=_string_list(args.get("include_sites"), maximum=10),
            exclude_sites=_string_list(args.get("exclude_sites"), maximum=10),
        )
        return {
            "source": "brave_search",
            "query": result.query,
            "item_count": len(result.items),
            "items": [
                {
                    "title": item.title,
                    "url": item.url,
                    "snippets": item.snippets,
                }
                for item in result.items
            ],
        }


def _object_schema(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None:
        return default
    parsed = int(value)
    if parsed < minimum:
        return default
    return min(parsed, maximum)


def _optional_bounded_int(value: object, *, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed < minimum:
        return minimum
    return min(parsed, maximum)


def _string_list(value: object, *, maximum: int) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("站点列表必须是字符串数组")
    items = [str(item).strip() for item in value if str(item).strip()]
    return items[:maximum] or None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
