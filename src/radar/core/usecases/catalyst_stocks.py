from __future__ import annotations

from collections.abc import Callable

from radar.core.config import RadarConfig
from radar.core.messages import CatalystStockMention
from radar.core.storage import connect, migrate_market_db
from radar.core.usecases.stock_evidence_chain.matcher import StockMatcher, load_stocks

CatalystStockDetector = Callable[[str], list[CatalystStockMention]]


def load_catalyst_stock_detector(config: RadarConfig) -> CatalystStockDetector | None:
    """从 market stock_basic 缓存构造中文标的识别器；没有缓存时保持沉默。"""

    conn = connect(config.market_database_path)
    try:
        migrate_market_db(conn)
        stocks = load_stocks(conn)
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
