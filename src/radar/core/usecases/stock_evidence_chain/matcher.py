from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter

from radar.core.usecases.stock_evidence_chain.models import MessageRow, Stock

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
WEAK_EVENT_ONLY = ("策略会", "邀请", "日程", "安排")
EVIDENCE_FAMILIES: dict[str, tuple[int, tuple[str, ...]]] = {
    "catalyst": (3, ("涨价", "提价", "缺货", "供不应求", "订单", "锁单", "排产", "量产", "验证", "中标", "业绩上修", "满产")),
    "roadshow": (3, ("董秘", "IR", "反路演", "1v1", "一对一", "调研", "电话会议")),
    "research": (2, ("深度报告", "首次覆盖", "点评", "更新", "纪要", "测算", "专家会", "专家交流")),
    "push": (2, ("强推", "强烈推荐", "重点推荐", "继续推荐", "首推", "金股", "call")),
    "price": (1, ("涨停", "成交额", "放量", "大涨", "异动")),
}


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
    rows = conn.execute("SELECT data FROM tushare_cache WHERE api_name='stock_basic'").fetchall()
    by_code: dict[str, Stock] = {}
    for row in rows:
        for item in json.loads(row["data"]):
            ts_code = str(item.get("ts_code") or "")
            symbol = str(item.get("symbol") or "")
            name = str(item.get("name") or "")
            if ts_code and symbol and usable_stock_name(name):
                by_code[ts_code] = Stock(ts_code=ts_code, symbol=symbol, name=name)
    return sorted(by_code.values(), key=lambda item: len(item.name), reverse=True)


def usable_stock_name(name: str) -> bool:
    return len(name) >= 2 and not name.startswith(("*ST", "ST"))


def has_stock_context(text: str, stock: Stock) -> bool:
    if len(stock.name) > 3 and stock.name not in CONTEXT_REQUIRED_STOCK_NAMES:
        return True
    markers = (
        f"#{stock.name}", f"${stock.name}", f"【{stock.name}】", f"[{stock.name}]",
        f"「{stock.name}」", f"《{stock.name}》", f"{stock.name}：", f"{stock.name}:",
    )
    return any(marker in text for marker in markers)


def evidence_features(row: MessageRow, stock: Stock) -> tuple[tuple[str, ...], int]:
    families: Counter[str] = Counter()
    for family, (score, keywords) in EVIDENCE_FAMILIES.items():
        if _near_stock(row.raw_content, stock, keywords):
            families[family] = score
    if set(families) == {"roadshow"} and row.category == "event" and any(term in row.raw_content for term in WEAK_EVENT_ONLY):
        return (), 0
    return tuple(sorted(families)), sum(families.values())


def _near_stock(text: str, stock: Stock, keywords: tuple[str, ...], radius: int = 90) -> bool:
    for term in (stock.name, stock.symbol, stock.ts_code):
        if not term:
            continue
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            chunk = text[max(0, index - radius) : index + len(term) + radius]
            if any(keyword in chunk for keyword in keywords):
                return True
            start = index + len(term)
    return False


def content_fingerprint(text: str) -> str:
    normalized = URL_RE.sub("", text)
    normalized = SPACE_RE.sub("", normalized)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()
