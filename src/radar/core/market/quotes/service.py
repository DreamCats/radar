from __future__ import annotations

from collections.abc import Sequence

import httpx

from radar.core.config import RadarConfig
from radar.core.market.quotes.models import MinuteQuotePoint, RealtimeQuote
from radar.core.market.quotes.sina import parse_sina_realtime_response, sina_realtime_url
from radar.core.market.quotes.tencent import (
    parse_tencent_minute_response,
    parse_tencent_realtime_response,
    tencent_minute_url,
    tencent_realtime_url,
)

PUBLIC_QUOTE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.sina.com.cn/",
}


def get_public_realtime_quote(
    config: RadarConfig,
    *,
    ts_code: str,
    sources: Sequence[str] = ("tencent", "sina"),
) -> RealtimeQuote | None:
    """查询公开实时行情；失败时返回 None，由上层决定是否降级展示。"""

    for source in sources:
        quote = _get_realtime_from_source(config, source=source, ts_code=ts_code)
        if quote is not None and quote.close is not None and quote.open is not None:
            return quote
    return None


def get_tencent_intraday_minutes(config: RadarConfig, *, ts_code: str) -> list[MinuteQuotePoint]:
    text = _get_text(config, tencent_minute_url(ts_code))
    return parse_tencent_minute_response(text, ts_code=ts_code)


def _get_realtime_from_source(
    config: RadarConfig,
    *,
    source: str,
    ts_code: str,
) -> RealtimeQuote | None:
    try:
        if source == "tencent":
            return parse_tencent_realtime_response(
                _get_text(config, tencent_realtime_url(ts_code)),
                ts_code=ts_code,
            )
        if source == "sina":
            return parse_sina_realtime_response(
                _get_text(config, sina_realtime_url(ts_code)),
                ts_code=ts_code,
            )
    except (httpx.HTTPError, ValueError):
        return None
    return None


def _get_text(config: RadarConfig, url: str) -> str:
    with httpx.Client(timeout=config.market.timeout, headers=PUBLIC_QUOTE_HEADERS) as client:
        response = client.get(url)
        response.raise_for_status()
        if "sinajs" in url:
            response.encoding = "gb18030"
        return response.text
