from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Iterable

from radar.core.messages import CatalystStockMention
from radar.core.usecases.premarket_signal.models import ConceptSource

_IGNORED_CONCEPT_NAMES = {
    "AB股",
    "AH股",
    "A股",
    "B股",
    "创业板综",
    "参股新三板",
    "标准普尔",
    "富时罗素",
    "机构重仓",
    "沪股通",
    "深股通",
    "上证180_",
    "上证380",
    "融资融券",
    "深成500",
    "深证100R",
    "预亏预减",
    "预盈预增",
    "证金持股",
    "转债标的",
    "昨日触板",
    "昨日连板",
    "昨日涨停",
}


@dataclass(frozen=True)
class ConceptMember:
    concept_code: str
    concept_name: str
    source: ConceptSource


def load_concept_members(
    conn: sqlite3.Connection | None,
) -> tuple[dict[str, list[ConceptMember]], ConceptSource, int]:
    if conn is None or not _table_exists(conn, "tushare_cache"):
        return {}, "none", 0

    ths_index = _latest_rows(_cached_rows(conn, "ths_index"))
    ths_members = _latest_rows(_cached_rows(conn, "ths_member"))
    if ths_members:
        return _concept_members(ths_members, _concept_names(ths_index), source="ths")

    dc_index = _latest_rows(_cached_rows(conn, "dc_concept"))
    dc_members = _latest_rows(_cached_rows(conn, "dc_concept_cons"))
    if not dc_members:
        dc_index = _latest_rows(_cached_rows(conn, "dc_index"))
        dc_members = _latest_rows(_cached_rows(conn, "dc_member"))
    if dc_members:
        return _concept_members(dc_members, _concept_names(dc_index), source="dc")

    return {}, "none", 0


def memberships_for_stock(
    stock: CatalystStockMention,
    concept_members: dict[str, list[ConceptMember]],
) -> list[ConceptMember]:
    seen: set[str] = set()
    members: list[ConceptMember] = []
    for key in (stock.ts_code, stock.stock_name):
        if not key:
            continue
        for member in concept_members.get(key, []):
            if member.concept_code in seen:
                continue
            seen.add(member.concept_code)
            members.append(member)
    return members


def _concept_names(rows: Iterable[dict[str, object]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in rows:
        code = _first_text(row, "ts_code", "theme_code", "index_code", "concept_code")
        name = _first_text(row, "name", "concept_name", "theme_name")
        if code and name:
            names[code] = name
    return names


def _concept_members(
    rows: Iterable[dict[str, object]],
    concept_names: dict[str, str],
    *,
    source: ConceptSource,
) -> tuple[dict[str, list[ConceptMember]], ConceptSource, int]:
    by_stock: dict[str, list[ConceptMember]] = {}
    concept_codes: set[str] = set()
    for row in rows:
        concept_code = _concept_code(row, source)
        stock_code = _stock_code(row, source)
        if not concept_code or not stock_code:
            continue
        concept_name = concept_names.get(concept_code) or _first_text(row, "concept_name", "theme_name")
        if not concept_name:
            concept_name = concept_code
        if _is_ignored_concept(concept_name):
            continue
        concept_codes.add(concept_code)
        member = ConceptMember(concept_code=concept_code, concept_name=concept_name, source=source)
        by_stock.setdefault(stock_code, []).append(member)
        stock_name = _first_text(row, "name", "con_name", "stock_name")
        if stock_name:
            by_stock.setdefault(stock_name, []).append(member)
    return by_stock, source, len(concept_codes)


def _cached_rows(conn: sqlite3.Connection, api_name: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cache_row in conn.execute("SELECT data FROM tushare_cache WHERE api_name = ?", (api_name,)).fetchall():
        try:
            data = json.loads(cache_row["data"])
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            rows.extend(row for row in data if isinstance(row, dict))
    return rows


def _latest_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    dates = [str(row.get("trade_date") or row.get("date") or "") for row in rows]
    dates = [date for date in dates if date]
    if not dates:
        return rows
    latest = max(dates)
    return [row for row in rows if str(row.get("trade_date") or row.get("date") or "") == latest]


def _concept_code(row: dict[str, object], source: ConceptSource) -> str:
    if source == "dc":
        return _first_text(row, "theme_code", "ts_code", "index_code", "concept_code")
    return _first_text(row, "ts_code", "concept_code", "index_code")


def _stock_code(row: dict[str, object], source: ConceptSource) -> str:
    if source == "dc":
        if _first_text(row, "theme_code"):
            return _first_text(row, "ts_code", "con_code", "stock_code", "stock_ts_code")
        return _first_text(row, "con_code", "stock_code", "stock_ts_code")
    return _first_text(row, "con_code", "stock_code", "stock_ts_code")


def _first_text(row: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _is_ignored_concept(name: str) -> bool:
    if name.endswith("板块"):
        return True
    return name in _IGNORED_CONCEPT_NAMES


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None
