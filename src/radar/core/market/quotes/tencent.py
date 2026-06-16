from __future__ import annotations

import json
import re
from typing import Any

from radar.core.market.quotes.models import MinuteQuotePoint, RealtimeQuote
from radar.core.market.quotes.symbols import to_public_quote_code

TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
TENCENT_REALTIME_URL = "https://qt.gtimg.cn/q={quote_code}"


def tencent_minute_url(ts_code: str) -> str:
    return f"{TENCENT_MINUTE_URL}?code={to_public_quote_code(ts_code)}"


def tencent_realtime_url(ts_code: str) -> str:
    return TENCENT_REALTIME_URL.format(quote_code=to_public_quote_code(ts_code))


def parse_tencent_realtime_response(text: str, *, ts_code: str) -> RealtimeQuote | None:
    values = _realtime_values(text)
    if not values or len(values) < 6:
        return None
    code = ts_code.strip().upper()
    volume_lots = _float_at(values, 36)
    if volume_lots is None:
        volume_lots = _float_at(values, 6)
    amount_10k_yuan = _float_at(values, 37)
    timestamp = _value_at(values, 30)
    return RealtimeQuote(
        ts_code=code,
        source="tencent",
        name=_value_at(values, 1),
        pre_close=_float_at(values, 4),
        open=_float_at(values, 5),
        high=_float_at(values, 33),
        low=_float_at(values, 34),
        close=_float_at(values, 3),
        volume_shares=int(volume_lots * 100) if volume_lots is not None else None,
        amount_yuan=amount_10k_yuan * 10000 if amount_10k_yuan is not None else None,
        bid1_price=_float_at(values, 9),
        bid1_volume_lots=_float_at(values, 10),
        ask1_price=_float_at(values, 19),
        ask1_volume_lots=_float_at(values, 20),
        timestamp=timestamp,
    )


def parse_tencent_minute_response(text: str, *, ts_code: str) -> list[MinuteQuotePoint]:
    payload = json.loads(text)
    lines = _minute_lines(payload, to_public_quote_code(ts_code))
    points: list[MinuteQuotePoint] = []
    prev_volume = 0
    prev_amount = 0.0
    for line in lines:
        point = _minute_point(line, prev_volume=prev_volume, prev_amount=prev_amount)
        if point is None:
            continue
        points.append(point)
        prev_volume = point.cum_volume_shares
        prev_amount = point.cum_amount_yuan
    return points


def _realtime_values(text: str) -> list[str]:
    match = re.search(r'="([^"]*)"', text)
    payload = match.group(1) if match else text
    return payload.strip().strip(";").split("~")


def _minute_lines(payload: Any, quote_code: str) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    stock_data = data.get(quote_code) or data.get(quote_code.upper())
    if not isinstance(stock_data, dict) and data:
        stock_data = next((item for item in data.values() if isinstance(item, dict)), None)
    if not isinstance(stock_data, dict):
        return []
    nested = stock_data.get("data")
    if isinstance(nested, list):
        return [item for item in nested if isinstance(item, str)]
    if isinstance(nested, dict):
        lines = nested.get("data")
        if isinstance(lines, list):
            return [item for item in lines if isinstance(item, str)]
    lines = stock_data.get("data")
    return [item for item in lines if isinstance(item, str)] if isinstance(lines, list) else []


def _minute_point(line: str, *, prev_volume: int, prev_amount: float) -> MinuteQuotePoint | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    time_value = _minute_time(parts[0])
    price = _float(parts[1])
    volume_lots = _float(parts[2])
    amount = _float(parts[3])
    if time_value is None or price is None or volume_lots is None or amount is None:
        return None
    cum_volume = int(volume_lots * 100)
    return MinuteQuotePoint(
        time=time_value,
        price=price,
        cum_volume_shares=cum_volume,
        cum_amount_yuan=amount,
        minute_volume_shares=cum_volume - prev_volume,
        minute_amount_yuan=amount - prev_amount,
    )


def _minute_time(value: str) -> str | None:
    if len(value) != 4 or not value.isdigit():
        return None
    return f"{value[:2]}:{value[2:]}"


def _value_at(values: list[str], index: int) -> str | None:
    if index >= len(values):
        return None
    value = values[index].strip()
    return value or None


def _float_at(values: list[str], index: int) -> float | None:
    value = _value_at(values, index)
    return _float(value)


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
