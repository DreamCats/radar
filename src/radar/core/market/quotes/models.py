from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

QuoteSource = Literal["tencent", "sina"]


class RealtimeQuote(BaseModel):
    ts_code: str
    source: QuoteSource
    name: str | None = None
    pre_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume_shares: int | None = None
    amount_yuan: float | None = None
    bid1_price: float | None = None
    bid1_volume_lots: float | None = None
    ask1_price: float | None = None
    ask1_volume_lots: float | None = None
    timestamp: str | None = None


class MinuteQuotePoint(BaseModel):
    time: str
    price: float
    cum_volume_shares: int
    cum_amount_yuan: float
    minute_volume_shares: int
    minute_amount_yuan: float
