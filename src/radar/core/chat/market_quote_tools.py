from __future__ import annotations

from typing import Any

from radar.core.chat.tools import ChatTool
from radar.core.config import RadarConfig
from radar.core.market.quotes import (
    RealtimeQuote,
    from_public_quote_code,
    get_public_realtime_quote,
)


INDEX_ALIASES = {
    "上证": "000001.SH",
    "上证指数": "000001.SH",
    "上证综指": "000001.SH",
    "沪指": "000001.SH",
    "大盘": "000001.SH",
    "上证50": "000016.SH",
    "沪深300": "000300.SH",
    "沪深300指数": "000300.SH",
    "中证500": "000905.SH",
    "中证500指数": "000905.SH",
    "中证1000": "000852.SH",
    "中证1000指数": "000852.SH",
    "深证成指": "399001.SZ",
    "深成指": "399001.SZ",
    "创业板指": "399006.SZ",
    "创业板指数": "399006.SZ",
    "科创50": "000688.SH",
    "科创50指数": "000688.SH",
}


class RadarMarketQuoteTools:
    def __init__(self, config: RadarConfig):
        self.config = config

    def tools(self) -> list[ChatTool]:
        return [self.realtime_quote_tool()]

    def realtime_quote_tool(self) -> ChatTool:
        return ChatTool(
            name="radar_get_realtime_quote",
            description=(
                "查询腾讯/新浪公开实时行情。"
                "支持 ts_code、公开行情代码和指数别名。"
                "用于盘中上证指数、个股实时价等，不依赖 Tushare 实时权限。"
            ),
            input_schema=_object_schema(
                {
                    "symbol": {
                        "type": "string",
                        "description": (
                            "例如 000001.SH、sh000001、上证指数、沪深300、000811.SZ。"
                        ),
                    },
                    "source": {"type": "string", "enum": ["tencent", "sina"]},
                },
                required=["symbol"],
            ),
            handler=self.realtime_quote,
        )

    def realtime_quote(self, args: dict[str, Any]) -> dict[str, Any]:
        symbol = str(args["symbol"]).strip()
        ts_code = resolve_quote_symbol(symbol)
        source = _optional_source(args.get("source"))
        sources = (source,) if source else ("tencent", "sina")
        quote = get_public_realtime_quote(self.config, ts_code=ts_code, sources=sources)
        if quote is None:
            return {
                "found": False,
                "symbol": symbol,
                "ts_code": ts_code,
                "requested_source": source,
            }
        result = quote.model_dump(mode="json")
        result.update(
            {
                "found": True,
                "symbol": symbol,
                "change": _change(quote),
                "pct_chg": _pct_chg(quote),
            }
        )
        return result


def resolve_quote_symbol(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("symbol 不能为空")
    alias = INDEX_ALIASES.get(_normalize_alias(text))
    if alias:
        return alias
    lower = text.lower()
    if len(lower) == 8 and lower[:2] in {"sh", "sz", "bj"} and lower[2:].isdigit():
        return from_public_quote_code(lower)
    return text.upper()


def _change(quote: RealtimeQuote) -> float | None:
    if quote.close is None or quote.pre_close is None:
        return None
    return quote.close - quote.pre_close


def _pct_chg(quote: RealtimeQuote) -> float | None:
    change = _change(quote)
    if change is None or not quote.pre_close:
        return None
    return change / quote.pre_close * 100


def _optional_source(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text not in {"tencent", "sina"}:
        raise ValueError(f"不支持的行情源: {text}")
    return text


def _normalize_alias(value: str) -> str:
    return value.strip().replace(" ", "").lower()


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
