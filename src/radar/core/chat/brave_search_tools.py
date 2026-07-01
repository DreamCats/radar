from __future__ import annotations

from typing import Any

from radar.core.brave_search import BraveSearchError, search_context
from radar.core.chat.cninfo_disclosures import CninfoDisclosureError, search_cninfo_disclosures
from radar.core.chat.tools import ChatTool
from radar.core.config import RadarConfig
from radar.core.tushare import resolve_stock

DISCLOSURE_SITES = ["cninfo.com.cn", "sse.com.cn", "szse.cn"]

class RadarBraveSearchTools:
    def __init__(self, config: RadarConfig):
        self.config = config

    def tools(self) -> list[ChatTool]:
        return [self.search_web_tool(), self.search_stock_disclosures_tool()]

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

    def search_stock_disclosures_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_search_stock_disclosures",
            description=(
                "按股票、日期、关键词查询上市公司公告。优先读取巨潮结构化公告列表，"
                "无结果或失败时再搜索巨潮、上交所、深交所等官方披露站点。"
                "用于把报告原文转述升级为可验证公开来源；返回公告标题、时间、链接，不下载 PDF 正文。"
            ),
            input_schema=_object_schema(
                {
                    "stock": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "category": {
                        "type": "string",
                        "enum": [
                            "年报",
                            "半年报",
                            "一季报",
                            "三季报",
                            "业绩预告",
                            "权益分派",
                            "董事会",
                            "监事会",
                            "股东大会",
                            "日常经营",
                            "公司治理",
                            "中介报告",
                            "首发",
                            "增发",
                            "股权激励",
                            "配股",
                            "解禁",
                            "公司债",
                            "可转债",
                            "其他融资",
                            "股权变动",
                            "补充更正",
                            "澄清致歉",
                            "风险提示",
                            "特别处理和退市",
                            "退市整理期",
                        ],
                    },
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "count": {"type": "integer", "minimum": 1, "maximum": 10},
                    "max_tokens": {"type": "integer", "minimum": 1024, "maximum": 8192},
                    "include_sites": {"type": "array", "items": {"type": "string"}},
                },
                required=["stock"],
            ),
            handler=self.search_stock_disclosures,
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

    def search_stock_disclosures(self, args: dict[str, Any]) -> dict[str, Any]:
        stock = str(args["stock"]).strip()
        if not stock:
            raise ValueError("stock 不能为空")
        ts_code = _resolve_stock_safe(self.config, stock)
        keywords = _string_list(args.get("keywords"), maximum=8) or []
        category = _optional_str(args.get("category"))
        count = _bounded_int(args.get("count"), default=5, minimum=1, maximum=10)
        cninfo_result: dict[str, Any] | None = None
        cninfo_error: str | None = None
        try:
            cninfo_result = search_cninfo_disclosures(
                stock=stock,
                ts_code=ts_code,
                keywords=keywords,
                category=category,
                start_date=_optional_str(args.get("start_date")),
                end_date=_optional_str(args.get("end_date")),
                limit=count,
            )
        except (CninfoDisclosureError, ValueError) as exc:
            cninfo_error = str(exc)

        if cninfo_result and cninfo_result.get("items"):
            return {**cninfo_result, "ts_code": _result_ts_code(ts_code, cninfo_result)}

        query = _disclosure_query(
            stock,
            ts_code=ts_code,
            keywords=keywords,
            category=category,
            start_date=_optional_str(args.get("start_date")),
            end_date=_optional_str(args.get("end_date")),
        )
        include_sites = _string_list(args.get("include_sites"), maximum=10) or DISCLOSURE_SITES
        try:
            result = search_context(
                self.config,
                query,
                count=count,
                max_tokens=_bounded_int(
                    args.get("max_tokens"),
                    default=4096,
                    minimum=1024,
                    maximum=8192,
                ),
                max_tokens_per_url=None,
                threshold="balanced",
                include_sites=include_sites,
                exclude_sites=None,
            )
        except BraveSearchError as exc:
            if cninfo_result is not None:
                return {
                    **cninfo_result,
                    "ts_code": _result_ts_code(ts_code, cninfo_result),
                    "cninfo_error": cninfo_error,
                    "brave_error": str(exc),
                }
            return {
                "source": "cninfo",
                "scope": "cninfo_disclosure_list",
                "stock": stock,
                "ts_code": ts_code,
                "cninfo": cninfo_result,
                "cninfo_error": cninfo_error,
                "brave_error": str(exc),
                "item_count": 0,
                "items": [],
            }
        return {
            "source": "brave_search",
            "scope": "official_disclosure_sites",
            "stock": stock,
            "ts_code": ts_code,
            "cninfo": cninfo_result,
            "cninfo_error": cninfo_error,
            "query": result.query,
            "include_sites": include_sites,
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


def _resolve_stock_safe(config: RadarConfig, stock: str) -> str | None:
    try:
        return resolve_stock(config, stock)
    except Exception:
        return None


def _result_ts_code(ts_code: str | None, cninfo_result: dict[str, Any]) -> str | None:
    if ts_code:
        return ts_code
    code = str(cninfo_result.get("code") or "").strip()
    if not code:
        return None
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8", "9")):
        return f"{code}.BJ"
    return None


def _disclosure_query(
    stock: str,
    *,
    ts_code: str | None,
    keywords: list[str],
    category: str | None,
    start_date: str | None,
    end_date: str | None,
) -> str:
    parts = [stock]
    if ts_code:
        parts.append(ts_code.split(".", 1)[0])
    if category:
        parts.append(category)
    parts.extend(keywords)
    parts.extend(["公告", "公司公告", "交易所"])
    if start_date or end_date:
        parts.append(f"{start_date or ''} {end_date or ''}".strip())
    return " ".join(part for part in parts if part)
