from __future__ import annotations

import re
from dataclasses import dataclass

from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationEvidence,
    CatalystValuationStockContext,
)

_MONEY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)\s*"
    r"(?:万亿|亿元|亿|千万|万元|百万|万美元|亿美元|人民币|美元|美金|元)"
    r"(?:\s*/\s*(?:吨|台|套|片|颗|件|公斤|kg|g|w|kw|mw|gw|kwh|mwh|gwh|平|平方米|亩))?",
    re.IGNORECASE,
)
_QUANTITY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)\s*"
    r"(?:万吨|吨|万台|台|万套|套|万片|片|万颗|颗|万件|件|公斤|kg|g|"
    r"gw|mw|kw|w|gwh|mwh|kwh|亩|平方米|平|条线|条)",
    re.IGNORECASE,
)
_PERCENT_PATTERN = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*%")
_MULTIPLE_PATTERN = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*(?:倍|x|X)")
_CLAUSE_BOUNDARY_PATTERN = re.compile(r"[。！？!?；;\n\r]")

_VALUE_TERMS = (
    "订单",
    "合同",
    "中标",
    "签约",
    "采购",
    "招标",
    "收入",
    "营收",
    "利润",
    "净利",
    "毛利",
    "盈利",
    "业绩",
    "产能",
    "产量",
    "销量",
    "出货",
    "交付",
    "装机",
    "排产",
    "满产",
    "产线",
    "良率",
    "利用率",
    "单价",
    "涨价",
    "提价",
    "ASP",
    "价格",
    "客户",
    "份额",
    "市占率",
    "净利率",
    "毛利率",
    "市值",
    "估值",
    "PE",
    "pe",
)

_PERCENT_VALUE_TERMS = (
    "涨价",
    "提价",
    "毛利率",
    "净利率",
    "市占率",
    "份额",
    "增长",
    "增速",
    "预增",
    "上修",
    "盈利",
    "利润",
    "收入",
    "营收",
    "良率",
    "利用率",
)

_MARKET_SIZE_TERMS = (
    "市场",
    "市场空间",
    "市场规模",
    "行业空间",
    "行业规模",
    "赛道",
    "空间",
)

_WEAK_RATIO_TERMS = (
    "价值量",
    "价值占比",
    "工序",
    "环节",
)


@dataclass(frozen=True)
class ValuationEvidenceMatch:
    terms: list[str]
    numbers: list[str]


def extract_display_numbers(content: str) -> list[str]:
    """原文展示用数字高亮，不参与是否保留标的的判断。"""

    values = [
        *(match.group(0) for match in _MONEY_PATTERN.finditer(content)),
        *(match.group(0) for match in _QUANTITY_PATTERN.finditer(content)),
        *(match.group(0) for match in _PERCENT_PATTERN.finditer(content)),
        *(match.group(0) for match in _MULTIPLE_PATTERN.finditer(content)),
    ]
    return _unique(values)


def filter_contexts_by_valuation_evidence(
    contexts: list[CatalystValuationStockContext],
) -> list[CatalystValuationStockContext]:
    """只保留能接到估值推演的标的证据。"""

    kept: list[CatalystValuationStockContext] = []
    for context in contexts:
        evidence: list[CatalystValuationEvidence] = []
        for item in context.evidence:
            match = match_valuation_evidence(
                item.content,
                stock_name=context.stock_name,
                ts_code=context.ts_code,
                stock_mentions_count=item.stock_mentions_count,
            )
            if match is None:
                continue
            evidence.append(
                item.model_copy(
                    update={
                        "valuation_terms": match.terms,
                        "valuation_numbers": match.numbers,
                    }
                )
            )
        if not evidence:
            continue
        kept.append(
            context.model_copy(
                update={
                    "evidence": evidence,
                    "first_message_time": min(item.message_time for item in evidence),
                    "latest_message_time": max(item.latest_message_time for item in evidence),
                }
            )
        )
    kept.sort(key=lambda item: (item.latest_message_time, len(item.evidence), item.stock_key), reverse=True)
    return kept


def match_valuation_evidence(
    content: str,
    *,
    stock_name: str,
    ts_code: str | None,
    stock_mentions_count: int,
) -> ValuationEvidenceMatch | None:
    if stock_mentions_count <= 1:
        return _match_text(content)

    matches: list[ValuationEvidenceMatch] = []
    for window in _stock_windows(content, stock_name=stock_name, ts_code=ts_code):
        match = _match_text(window)
        if match is not None:
            matches.append(match)
    if not matches:
        return None
    return ValuationEvidenceMatch(
        terms=_unique(term for match in matches for term in match.terms),
        numbers=_unique(number for match in matches for number in match.numbers),
    )


def _match_text(text: str) -> ValuationEvidenceMatch | None:
    terms = _matched_terms(text)
    if not terms:
        return None

    money = _usable_money_numbers(text)
    quantity = _usable_quantity_numbers(text)
    percent = _usable_percent_numbers(text) if any(term in text for term in _PERCENT_VALUE_TERMS) else []
    multiple = _usable_multiple_numbers(text) if any(term in text for term in ("估值", "市值", "PE", "pe")) else []
    numbers = _unique([*money, *quantity, *percent, *multiple])
    if not numbers:
        return None
    return ValuationEvidenceMatch(terms=terms, numbers=numbers)


def _stock_windows(content: str, *, stock_name: str, ts_code: str | None) -> list[str]:
    tokens = [stock_name.strip()]
    if ts_code:
        tokens.extend([ts_code.strip(), ts_code.split(".", 1)[0].strip()])
    windows: list[str] = []
    for token in _unique(token for token in tokens if token):
        for match in re.finditer(re.escape(token), content, re.IGNORECASE):
            start, end = _clause_bounds(content, match.start(), match.end())
            windows.append(content[start:end])
    return windows


def _clause_bounds(content: str, start_index: int, end_index: int) -> tuple[int, int]:
    start = 0
    for match in _CLAUSE_BOUNDARY_PATTERN.finditer(content, 0, start_index):
        start = match.end()

    next_boundary = _CLAUSE_BOUNDARY_PATTERN.search(content, end_index)
    end = next_boundary.start() if next_boundary else len(content)
    if end - start > 280:
        start = max(start, start_index - 80)
        end = min(end, end_index + 180)
    return start, end


def _matched_terms(text: str) -> list[str]:
    return [term for term in _VALUE_TERMS if term in text]


def _usable_money_numbers(text: str) -> list[str]:
    values: list[str] = []
    for match in _MONEY_PATTERN.finditer(text):
        if _near_market_size_term(text, match.start(), match.end()):
            continue
        values.append(match.group(0))
    return _unique(values)


def _usable_quantity_numbers(text: str) -> list[str]:
    return _unique(match.group(0) for match in _QUANTITY_PATTERN.finditer(text))


def _usable_percent_numbers(text: str) -> list[str]:
    values: list[str] = []
    for match in _PERCENT_PATTERN.finditer(text):
        if _near_weak_ratio_term(text, match.start(), match.end()):
            continue
        values.append(match.group(0))
    return _unique(values)


def _usable_multiple_numbers(text: str) -> list[str]:
    return _unique(match.group(0) for match in _MULTIPLE_PATTERN.finditer(text))


def _near_market_size_term(text: str, start: int, end: int) -> bool:
    around = text[max(0, start - 8) : min(len(text), end + 8)]
    return any(term in around for term in _MARKET_SIZE_TERMS)


def _near_weak_ratio_term(text: str, start: int, end: int) -> bool:
    around = text[max(0, start - 8) : min(len(text), end + 8)]
    return any(term in around for term in _WEAK_RATIO_TERMS)


def _unique(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
