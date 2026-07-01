from __future__ import annotations

import re
from dataclasses import dataclass

from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationEvidence,
    CatalystValuationStockContext,
)

# 群消息里常用 e/E 表示“亿”，但不能把 1e9、1e-3 这类科学计数法吞成金额。
_MONEY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)\s*"
    r"(?:万亿|亿元|亿|千万|万元|百万|万美元|亿美元|人民币|美元|美金|元|[eE](?![A-Za-z0-9]|[+-]\d))"
    r"(?:\s*/\s*(?:吨|台|套|片|颗|件|公斤|kg|gwh|mwh|kwh|gw|mw|kw|w|平方米|平|亩))?",
    re.IGNORECASE,
)
_QUANTITY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)\s*"
    r"(?:万吨|万台|万套|万片|万颗|万件|吨|台|套|片|颗|件|公斤|kg|"
    r"gwh|mwh|kwh|gw|mw|kw|w|平方米|平|亩|条线)",
    re.IGNORECASE,
)
_PERCENT_PATTERN = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*%")
_MULTIPLE_PATTERN = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*(?:倍|x|X)")
_MULTI_STOCK_WINDOW_BOUNDARY_PATTERN = re.compile(r"[。！？!?；;\n\r#【、]")
_MULTI_STOCK_ROLE_TAIL_PATTERN = re.compile(
    r"^(?:等|及|和|与)?(?:头部|核心|下游|终端|海外|国内|主要)?(?:客户|供应商|股东)"
    r"|^(?:已)?(?:取得对公司控制权|对公司|合资设立|共同设立|合作设立)"
)
_LEADING_SOURCE_BRACKET_PATTERN = re.compile(r"[【\[]([^】\]]{1,32})[】\]]")
_SOURCE_ROLE_TAIL_PATTERN = re.compile(r"^([\u4e00-\u9fffA-Za-z0-9]{2,12})(?:董事长|董秘|高管|专家|交流|电话会|调研|纪要|路演)")
_SOURCE_ROLE_GENERIC_SUBJECTS = {"公司", "本次", "今日", "会议", "电话", "专家", "高管", "董秘", "董事长"}

_VALUE_TERMS = (
    "首单",
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

_PRICE_ONLY_TERMS = {
    "ASP",
    "价格",
    "单价",
    "涨价",
    "提价",
}

_OPERATING_ANCHOR_TERMS = {
    "首单",
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
}

_PLAIN_YUAN_PATTERN = re.compile(r"^(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)\s*元$")
_TINY_COUNT_PATTERN = re.compile(r"^(?:1(?:\.0+)?|一)\s*(?:台|套|片|颗|件)$")


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
        evidence.sort(key=_evidence_sort_key, reverse=True)
        next_context = context.model_copy(
            update={
                "evidence": evidence,
                "first_message_time": min(item.message_time for item in evidence),
                "latest_message_time": max(item.latest_message_time for item in evidence),
            }
        )
        if not _is_reportable_stock_context(next_context):
            continue
        kept.append(next_context)
    kept.sort(key=_stock_context_sort_key, reverse=True)
    return kept


def _is_reportable_stock_context(context: CatalystValuationStockContext) -> bool:
    return _has_direct_anchor(context) or _has_operating_anchor(context)


def _stock_context_sort_key(context: CatalystValuationStockContext) -> tuple[object, ...]:
    numbers = _unique(number for item in context.evidence for number in item.valuation_numbers)
    return (
        _has_direct_operating_anchor(context),
        _has_operating_anchor(context),
        _has_direct_anchor(context),
        len(context.evidence) >= 2,
        len(context.evidence),
        len(numbers),
        context.latest_message_time,
        context.stock_key,
    )


def _evidence_sort_key(item: CatalystValuationEvidence) -> tuple[object, ...]:
    return (
        _has_operating_terms(item.valuation_terms),
        item.stock_mentions_count <= 1,
        len(item.valuation_numbers),
        item.latest_message_time,
        item.message_id,
    )


def _has_direct_operating_anchor(context: CatalystValuationStockContext) -> bool:
    return any(
        item.stock_mentions_count <= 1 and _has_operating_terms(item.valuation_terms)
        for item in context.evidence
    )


def _has_direct_anchor(context: CatalystValuationStockContext) -> bool:
    return any(item.stock_mentions_count <= 1 for item in context.evidence)


def _has_operating_anchor(context: CatalystValuationStockContext) -> bool:
    return any(_has_operating_terms(item.valuation_terms) for item in context.evidence)


def _has_operating_terms(terms: list[str]) -> bool:
    return any(term in _OPERATING_ANCHOR_TERMS for term in terms)


def match_valuation_evidence(
    content: str,
    *,
    stock_name: str,
    ts_code: str | None,
    stock_mentions_count: int,
) -> ValuationEvidenceMatch | None:
    if _is_source_role_mention(content, stock_name):
        return None
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
    if _is_weak_numeric_anchor(terms, money=money, quantity=quantity, percent=percent, multiple=multiple):
        return None
    return ValuationEvidenceMatch(terms=terms, numbers=numbers)


def _stock_windows(content: str, *, stock_name: str, ts_code: str | None) -> list[str]:
    tokens = [stock_name.strip()]
    if ts_code:
        tokens.extend([ts_code.strip(), ts_code.split(".", 1)[0].strip()])
    windows: list[str] = []
    for token in _unique(token for token in tokens if token):
        for match in re.finditer(re.escape(token), content, re.IGNORECASE):
            start, end = _multi_stock_window_bounds(content, match.start(), match.end())
            window = content[start:end]
            if _is_multi_stock_role_window(window, token):
                continue
            windows.append(window)
    return windows


def _multi_stock_window_bounds(content: str, start_index: int, end_index: int) -> tuple[int, int]:
    next_boundary = _MULTI_STOCK_WINDOW_BOUNDARY_PATTERN.search(content, end_index)
    end = next_boundary.start() if next_boundary else len(content)
    if end - start_index > 280:
        end = min(end, end_index + 180)
    return start_index, end


def _is_multi_stock_role_window(window: str, token: str) -> bool:
    text = window.lstrip()
    if not text.lower().startswith(token.lower()):
        return False
    tail = text[len(token) :].lstrip("】])）:： ")
    return bool(_MULTI_STOCK_ROLE_TAIL_PATTERN.match(tail[:32]))


def _is_source_role_mention(content: str, stock_name: str) -> bool:
    name = stock_name.strip()
    if not name:
        return False
    match = _LEADING_SOURCE_BRACKET_PATTERN.search(content[:48])
    if match is None or name not in match.group(1):
        return False
    if name in content[match.end() :]:
        return False
    tail = content[match.end() : match.end() + 48].lstrip(" ：:｜|-—")
    subject_match = _SOURCE_ROLE_TAIL_PATTERN.match(tail)
    if subject_match is None:
        return False
    return subject_match.group(1) not in _SOURCE_ROLE_GENERIC_SUBJECTS


def _matched_terms(text: str) -> list[str]:
    return [term for term in _VALUE_TERMS if term in text]


def _usable_money_numbers(text: str) -> list[str]:
    values: list[str] = []
    for match in _MONEY_PATTERN.finditer(text):
        if _near_market_size_term(text, match.start(), match.end()):
            continue
        value = match.group(0)
        if _is_plain_yuan_price(value):
            continue
        values.append(value)
    return _unique(values)


def _usable_quantity_numbers(text: str) -> list[str]:
    values: list[str] = []
    for match in _QUANTITY_PATTERN.finditer(text):
        value = match.group(0)
        if _is_tiny_count(value):
            continue
        values.append(value)
    return _unique(values)


def _usable_percent_numbers(text: str) -> list[str]:
    values: list[str] = []
    for match in _PERCENT_PATTERN.finditer(text):
        if _near_weak_ratio_term(text, match.start(), match.end()):
            continue
        values.append(match.group(0))
    return _unique(values)


def _usable_multiple_numbers(text: str) -> list[str]:
    return _unique(match.group(0) for match in _MULTIPLE_PATTERN.finditer(text))


def _is_weak_numeric_anchor(
    terms: list[str],
    *,
    money: list[str],
    quantity: list[str],
    percent: list[str],
    multiple: list[str],
) -> bool:
    term_set = set(terms)
    if term_set and term_set <= _PRICE_ONLY_TERMS:
        return True
    if percent and not money and not quantity and not multiple:
        return True
    if multiple and not money and not quantity and not percent:
        return True
    if money and not quantity and not percent and not multiple:
        return all(_is_plain_yuan_price(value) for value in money)
    return False


def _is_plain_yuan_price(value: str) -> bool:
    return bool(_PLAIN_YUAN_PATTERN.fullmatch(value.strip()))


def _is_tiny_count(value: str) -> bool:
    return bool(_TINY_COUNT_PATTERN.fullmatch(value.strip()))


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
