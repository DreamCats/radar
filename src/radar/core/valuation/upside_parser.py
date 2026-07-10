from __future__ import annotations

import re
from typing import Any

from radar.core.storage.valuation_store import ValuationMeasurementItemInput

POSITIVE_STATUSES = ("显著空间", "有空间但需验证")
_TS_CODE_RE = re.compile(r"\b(\d{6}\.(?:SH|SZ|BJ))\b", re.IGNORECASE)


def parse_upside_measurement_items(content: str) -> tuple[list[ValuationMeasurementItemInput], str | None]:
    for headers, rows in _markdown_tables(content):
        if not _is_upside_table(headers):
            continue
        items = [_row_to_item(headers, row) for row in rows]
        items = [item for item in items if item.name]
        if items:
            return items, None
    return [], "未找到可解析的空间测算总表"


def _markdown_tables(content: str) -> list[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        if not _is_table_row(lines[index]):
            index += 1
            continue
        block: list[str] = []
        while index < len(lines) and _is_table_row(lines[index]):
            block.append(lines[index])
            index += 1
        parsed = [_split_row(line) for line in block]
        parsed = [row for row in parsed if row]
        if len(parsed) < 2:
            continue
        headers = parsed[0]
        body_rows = parsed[2:] if _is_separator_row(parsed[1]) else parsed[1:]
        if headers and body_rows:
            tables.append((headers, body_rows))
    return tables


def _row_to_item(headers: list[str], row: list[str]) -> ValuationMeasurementItemInput:
    raw = {headers[index]: row[index] for index in range(min(len(headers), len(row)))}
    stock_text = _clean(_pick(raw, "标的"))
    name, ts_code = _split_stock(stock_text)
    status = _clean(_pick(raw, "状态"))
    notification_level = _clean_optional(_pick(raw, "通知等级"))
    return ValuationMeasurementItemInput(
        rank=_parse_rank(_pick(raw, "排名")),
        ts_code=ts_code,
        name=name,
        current_mv_text=_clean_optional(_pick(raw, "当前市值")),
        target_mv_text=_clean_optional(_pick(raw, "目标市值")),
        upside_text=_clean_optional(_pick(raw, "剩余空间")),
        valuation_status=status or None,
        confidence=_clean_optional(_pick(raw, "确定性")),
        anchor_type=_clean_optional(_pick(raw, "锚类型")),
        evidence_level=_clean_optional(_pick(raw, "证据等级")),
        gap_reason=_clean_optional(_pick(raw, "缺口原因")),
        notification_level=notification_level,
        key_validation=_clean_optional(_pick(raw, "关键验证")),
        risk_flags=_clean_optional(_pick(raw, "风险")),
        data_gaps=_clean_optional(_pick(raw, "数据缺口")),
        is_positive=_is_positive(status, notification_level),
        raw_row=raw,
    )


def _is_upside_table(headers: list[str]) -> bool:
    normalized = [_clean(header) for header in headers]
    return (
        any("标的" in header for header in normalized)
        and any("剩余空间" in header for header in normalized)
        and any("状态" in header for header in normalized)
    )


def _pick(raw: dict[str, str], label: str) -> str:
    for key, value in raw.items():
        if label in _clean(key):
            return value
    return ""


def _is_positive(status: str, notification_level: str | None) -> bool:
    if notification_level:
        return notification_level == "可通知"
    return any(value in status for value in POSITIVE_STATUSES)


def _split_stock(value: str) -> tuple[str, str | None]:
    match = _TS_CODE_RE.search(value)
    ts_code = match.group(1).upper() if match else None
    name = _TS_CODE_RE.sub("", value).strip(" -_/，,")
    return name or value, ts_code


def _parse_rank(value: str) -> int | None:
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [_clean(cell) for cell in stripped.split("|")]


def _is_separator_row(row: list[str]) -> bool:
    return all(cell and set(cell) <= {"-", ":", " "} for cell in row)


def _clean_optional(value: str) -> str | None:
    cleaned = _clean(value)
    return cleaned or None


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return " ".join(text.split())
