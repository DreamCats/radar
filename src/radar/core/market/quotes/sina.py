from __future__ import annotations

import re

from radar.core.market.quotes.models import RealtimeQuote
from radar.core.market.quotes.symbols import to_public_quote_code

SINA_REALTIME_URL = "https://hq.sinajs.cn/list={quote_code}"


def sina_realtime_url(ts_code: str) -> str:
    return SINA_REALTIME_URL.format(quote_code=to_public_quote_code(ts_code))


def parse_sina_realtime_response(text: str, *, ts_code: str) -> RealtimeQuote | None:
    values = _realtime_values(text)
    if len(values) < 10 or not values[0]:
        return None
    date_value = _value_at(values, 30)
    time_value = _value_at(values, 31)
    volume_shares = _int_at(values, 8)
    bid1_volume_shares = _float_at(values, 10)
    ask1_volume_shares = _float_at(values, 20)
    timestamp = (
        f"{date_value} {time_value}"
        if date_value and time_value
        else date_value or time_value
    )
    return RealtimeQuote(
        ts_code=ts_code.strip().upper(),
        source="sina",
        name=_value_at(values, 0),
        open=_float_at(values, 1),
        pre_close=_float_at(values, 2),
        close=_float_at(values, 3),
        high=_float_at(values, 4),
        low=_float_at(values, 5),
        volume_shares=volume_shares,
        amount_yuan=_float_at(values, 9),
        bid1_price=_float_at(values, 11),
        bid1_volume_lots=bid1_volume_shares / 100 if bid1_volume_shares is not None else None,
        ask1_price=_float_at(values, 21),
        ask1_volume_lots=ask1_volume_shares / 100 if ask1_volume_shares is not None else None,
        timestamp=timestamp,
    )


def _realtime_values(text: str) -> list[str]:
    match = re.search(r'="([^"]*)"', text)
    payload = match.group(1) if match else text
    return [item.strip() for item in payload.strip().strip(";").split(",")]


def _value_at(values: list[str], index: int) -> str | None:
    if index >= len(values):
        return None
    value = values[index].strip()
    return value or None


def _float_at(values: list[str], index: int) -> float | None:
    value = _value_at(values, index)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int_at(values: list[str], index: int) -> int | None:
    value = _float_at(values, index)
    return int(value) if value is not None else None
