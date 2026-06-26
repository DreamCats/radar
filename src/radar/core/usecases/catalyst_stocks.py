from __future__ import annotations

import sqlite3
from collections.abc import Callable

from radar.core.config import RadarConfig
from radar.core.messages import CatalystStockMention
from radar.core.storage import connect_readonly
from radar.core.tushare.stock_matcher import StockMatcher, load_stocks

CatalystStockDetector = Callable[[str], list[CatalystStockMention]]


def load_catalyst_stock_detector(config: RadarConfig) -> CatalystStockDetector | None:
    """从市场主数据构造中文标的识别器；没有主数据时保持沉默。"""

    if not config.market_database_path.exists():
        return None

    conn = connect_readonly(config.market_database_path)
    try:
        try:
            stocks = load_stocks(conn)
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            stocks = []
    finally:
        conn.close()
    if not stocks:
        return None
    matcher = StockMatcher(stocks)

    def detect(content: str) -> list[CatalystStockMention]:
        return [
            CatalystStockMention(ts_code=stock.ts_code, stock_name=stock.name)
            for stock in matcher.detect(content, strict=True)
        ]

    return detect
