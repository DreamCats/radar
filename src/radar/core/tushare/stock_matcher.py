from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass

from radar.core.tushare.stock_master import load_stock_master

CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
TS_CODE_RE = re.compile(r"\b\d{6}\.(?:SH|SZ|BJ)\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+")
SPACE_RE = re.compile(r"\s+")

# 这些名称本身是股票，但在消息里常作为行业词/券商来源出现，必须带股票语境才算命中。
CONTEXT_REQUIRED_STOCK_NAMES = {
    "机器人",
    "国联民生",
    "国泰海通",
    "申万宏源",
    "中信证券",
    "中信建投",
    "华泰证券",
    "方正证券",
    "兴业证券",
    "国信证券",
    "招商证券",
    "东方证券",
    "国金证券",
    "国海证券",
    "浙商证券",
    "财通证券",
}


@dataclass(frozen=True)
class Stock:
    ts_code: str
    symbol: str
    name: str


class StockMatcher:
    def __init__(self, stocks: list[Stock]) -> None:
        self.stocks = stocks
        self.by_symbol = {stock.symbol: stock for stock in stocks}
        self.by_ts_code = {stock.ts_code.upper(): stock for stock in stocks}
        self.by_name: dict[str, list[Stock]] = {}
        for stock in stocks:
            self.by_name.setdefault(stock.name, []).append(stock)
        names = sorted((re.escape(name) for name in self.by_name), key=len, reverse=True)
        self.name_pattern = re.compile("|".join(names)) if names else None

    def detect(self, text: str, *, strict: bool = True) -> list[Stock]:
        matched: dict[str, Stock] = {}
        upper_text = text.upper()
        for code in CODE_RE.findall(text):
            stock = self.by_symbol.get(code)
            if stock:
                matched[stock.ts_code] = stock
        for ts_code in TS_CODE_RE.findall(upper_text):
            stock = self.by_ts_code.get(ts_code.upper())
            if stock:
                matched[stock.ts_code] = stock
        if self.name_pattern:
            for match in self.name_pattern.finditer(text):
                name = match.group(0)
                for stock in self.by_name.get(name, []):
                    if not strict or has_stock_context(text, stock):
                        matched[stock.ts_code] = stock
        return list(matched.values())


def load_stocks(conn: sqlite3.Connection) -> list[Stock]:
    return [
        Stock(ts_code=row["ts_code"], symbol=row["symbol"], name=row["name"])
        for row in load_stock_master(conn, list_status="L")
        if usable_stock_name(row["name"])
    ]


def usable_stock_name(name: str) -> bool:
    return len(name) >= 2 and not name.startswith(("*ST", "ST"))


def has_stock_context(text: str, stock: Stock) -> bool:
    if len(stock.name) >= 3 and stock.name not in CONTEXT_REQUIRED_STOCK_NAMES:
        return True
    markers = (
        f"#{stock.name}",
        f"${stock.name}",
        f"【{stock.name}】",
        f"[{stock.name}]",
        f"「{stock.name}」",
        f"《{stock.name}》",
        f"{stock.name}：",
        f"{stock.name}:",
    )
    return any(marker in text for marker in markers)


def content_fingerprint(text: str) -> str:
    normalized = URL_RE.sub("", text)
    normalized = SPACE_RE.sub("", normalized)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()
