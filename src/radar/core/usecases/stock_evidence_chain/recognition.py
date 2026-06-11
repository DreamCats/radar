from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.usecases.stock_evidence_chain.theme_quality import (
    apply_theme_quality,
    is_primary_theme_candidate,
    theme_missing_summary,
    theme_sort_key,
)

MAX_THEMES_PER_STOCK = 8
MAX_RANKABLE_THEME_MEMBERS = 350


class StockEvidenceThemeContext(BaseModel):
    theme_id: str
    theme_name: str
    theme_type: str
    role: str
    confidence: float
    source_count: int
    reasons: list[str] = Field(default_factory=list)
    first_seen_date: str | None = None
    last_seen_date: str | None = None
    latest_trade_date: str | None = None
    member_count: int | None = None
    covered_member_count: int | None = None
    return_rank_5d: int | None = None
    stock_return_5d: float | None = None
    stock_return_20d: float | None = None
    amount_ratio_5d: float | None = None
    theme_return_median_5d: float | None = None
    is_theme_leader: bool = False
    is_theme_laggard: bool = False
    is_broad_theme: bool = False
    quality_score: float = 0.0
    quality_label: str = "待确认"
    quality_reasons: list[str] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class StockEvidenceRecognitionContext(BaseModel):
    state: str = "unknown"
    state_label: str = "证据不足"
    reasons: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _DailyMetric:
    return_5d: float | None
    return_20d: float | None
    amount_ratio_5d: float | None


def load_stock_theme_contexts(
    config: RadarConfig,
    ts_codes: list[str],
    *,
    as_of: datetime | None,
) -> dict[str, list[StockEvidenceThemeContext]]:
    codes = sorted({code.strip().upper() for code in ts_codes if code.strip()})
    if not codes:
        return {}

    with _connect_market(config.market_database_path) as conn:
        raw = _load_stock_memberships(conn, codes)
        if not raw:
            return {}
        selected = _select_memberships(raw)
        _attach_theme_rank_context(conn, selected, as_of=as_of)
        apply_theme_quality(selected, as_of=as_of)
        return selected


def primary_theme(themes: list[StockEvidenceThemeContext]) -> StockEvidenceThemeContext | None:
    for item in sorted(themes, key=theme_sort_key):
        if is_primary_theme_candidate(item):
            return item
    return None


def build_recognition_context(
    *,
    unique_trigger_count: int,
    market_summary: dict[str, Any],
    market_points: list[dict[str, Any]],
    themes: list[StockEvidenceThemeContext],
) -> StockEvidenceRecognitionContext:
    missing: list[str] = []
    reasons: list[str] = []
    primary = primary_theme(themes)
    if not themes:
        missing.append(theme_missing_summary(themes))
    elif primary is None:
        missing.append(theme_missing_summary(themes))
    else:
        reasons.append(
            f"主叙事候选：{primary.theme_name}（{primary.quality_label}，{primary.source_count} 个来源）"
        )

    return_since_first = _float(market_summary.get("return_since_first_point"))
    drawdown = _float(market_summary.get("drawdown_from_selected_high"))
    latest_amount_ratio = _latest_amount_ratio(market_points)
    theme = primary or (themes[0] if themes else None)
    return_5d = theme.stock_return_5d if theme else None
    return_20d = theme.stock_return_20d if theme else None
    amount_ratio = latest_amount_ratio or (theme.amount_ratio_5d if theme else None)

    if return_since_first is None and return_5d is None and return_20d is None:
        missing.append("缺价格涨跌证据，无法判断市场是否确认")
    if amount_ratio is None:
        missing.append("缺成交额放大证据")
    if theme and theme.return_rank_5d is None:
        missing.extend(theme.missing_evidence[:2])

    if _is_overheated(return_since_first, return_20d):
        reasons.append("短期涨幅较大，市场可能已经充分定价")
        return StockEvidenceRecognitionContext(
            state="overheated",
            state_label="已过热",
            reasons=reasons,
            missing_evidence=_dedupe(missing),
        )
    if return_since_first is not None and return_since_first > 0.18 and drawdown is not None and drawdown < -0.12:
        reasons.append("曾经上涨但从高点明显回撤，进入定价后回撤观察")
        return StockEvidenceRecognitionContext(
            state="pullback_after_pricing",
            state_label="定价后回撤",
            reasons=reasons,
            missing_evidence=_dedupe(missing),
        )
    if _is_confirmed(return_20d, return_since_first, drawdown, amount_ratio, theme):
        reasons.append("价格趋势、回撤和量能共同支持市场确认")
        return StockEvidenceRecognitionContext(
            state="confirmed",
            state_label="强确认",
            reasons=reasons,
            missing_evidence=_dedupe(missing),
        )
    if _is_just_confirmed(return_5d, return_since_first, amount_ratio, theme):
        reasons.append("短期价格和成交额开始确认，但还需要继续观察持续性")
        return StockEvidenceRecognitionContext(
            state="just_confirmed",
            state_label="刚确认",
            reasons=reasons,
            missing_evidence=_dedupe(missing),
        )
    if _is_rejected(unique_trigger_count, return_20d, return_since_first, theme):
        reasons.append("消息热度不低，但价格或主题内强弱没有跟上")
        return StockEvidenceRecognitionContext(
            state="rejected",
            state_label="市场不认",
            reasons=reasons,
            missing_evidence=_dedupe(missing),
        )

    if reasons:
        reasons.append("已有部分证据，但不足以给出市场确认")
    return StockEvidenceRecognitionContext(
        state="unknown",
        state_label="证据不足",
        reasons=reasons,
        missing_evidence=_dedupe(missing),
    )


def _connect_market(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    migrate_market_db(conn)
    return conn


def _load_stock_memberships(conn: sqlite3.Connection, ts_codes: list[str]) -> dict[str, list[StockEvidenceThemeContext]]:
    result: dict[str, list[StockEvidenceThemeContext]] = {code: [] for code in ts_codes}
    for chunk in _chunks(ts_codes, 300):
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT m.theme_id, m.ts_code, m.role, m.confidence, m.source_count,
                   m.reasons_json, m.first_seen_date, m.last_seen_date, m.latest_trade_date,
                   n.theme_name, n.theme_type
            FROM stock_theme_memberships m
            JOIN theme_nodes n ON n.theme_id = m.theme_id
            WHERE m.ts_code IN ({placeholders})
              AND n.status = 'active'
            """,
            chunk,
        ).fetchall()
        for row in rows:
            item = StockEvidenceThemeContext(
                theme_id=str(row["theme_id"]),
                theme_name=str(row["theme_name"]),
                theme_type=str(row["theme_type"]),
                role=str(row["role"]),
                confidence=round(float(row["confidence"] or 0), 4),
                source_count=int(row["source_count"] or 0),
                reasons=[str(value) for value in _json_list(row["reasons_json"])],
                first_seen_date=_optional_text(row["first_seen_date"]),
                last_seen_date=_optional_text(row["last_seen_date"]),
                latest_trade_date=_optional_text(row["latest_trade_date"]),
            )
            result.setdefault(str(row["ts_code"]), []).append(item)
    return {code: items for code, items in result.items() if items}


def _select_memberships(
    raw: dict[str, list[StockEvidenceThemeContext]],
) -> dict[str, list[StockEvidenceThemeContext]]:
    selected: dict[str, list[StockEvidenceThemeContext]] = {}
    for code, items in raw.items():
        ranked = sorted(items, key=_theme_sort_key)
        selected[code] = ranked[:MAX_THEMES_PER_STOCK]
    return selected


def _theme_sort_key(item: StockEvidenceThemeContext) -> tuple[int, int, float, int, str]:
    return theme_sort_key(item)


def _attach_theme_rank_context(
    conn: sqlite3.Connection,
    selected: dict[str, list[StockEvidenceThemeContext]],
    *,
    as_of: datetime | None,
) -> None:
    theme_ids = sorted({item.theme_id for items in selected.values() for item in items})
    if not theme_ids:
        return

    members_by_theme = _members_by_theme(conn, theme_ids)
    rankable_codes: set[str] = set()
    for theme_id, members in members_by_theme.items():
        if len(members) <= MAX_RANKABLE_THEME_MEMBERS:
            rankable_codes.update(members)

    metrics = _daily_metrics(conn, sorted(rankable_codes), as_of=as_of) if rankable_codes else {}
    ranked_by_theme = _ranked_by_theme(members_by_theme, metrics)

    for code, themes in selected.items():
        for item in themes:
            members = members_by_theme.get(item.theme_id, set())
            item.member_count = len(members)
            if not members:
                item.missing_evidence.append("主题成分为空，无法计算主题内强弱")
                continue
            if len(members) > MAX_RANKABLE_THEME_MEMBERS:
                item.missing_evidence.append("主题成分过多，暂不计算主题内排名")
                continue

            item.covered_member_count = len([member for member in members if member in metrics])
            stock_metric = metrics.get(code)
            if stock_metric is None:
                item.missing_evidence.append("本地行情缓存缺少该股近 5 日数据")
                continue

            item.stock_return_5d = _round(stock_metric.return_5d)
            item.stock_return_20d = _round(stock_metric.return_20d)
            item.amount_ratio_5d = _round(stock_metric.amount_ratio_5d)
            ranking = ranked_by_theme.get(item.theme_id, [])
            returns = [metric.return_5d for _, metric in ranking if metric.return_5d is not None]
            item.theme_return_median_5d = _round(_median(returns))
            for index, (member, _) in enumerate(ranking, start=1):
                if member == code:
                    item.return_rank_5d = index
                    break
            if item.return_rank_5d is None:
                item.missing_evidence.append("主题内可比股票行情覆盖不足")
                continue
            item.is_theme_leader = item.return_rank_5d <= max(3, math.ceil(len(ranking) * 0.2))
            item.is_theme_laggard = item.return_rank_5d > max(1, math.ceil(len(ranking) * 0.7))


def _members_by_theme(conn: sqlite3.Connection, theme_ids: list[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {theme_id: set() for theme_id in theme_ids}
    for chunk in _chunks(theme_ids, 300):
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT theme_id, ts_code FROM stock_theme_memberships WHERE theme_id IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            result.setdefault(str(row["theme_id"]), set()).add(str(row["ts_code"]))
    return result


def _daily_metrics(conn: sqlite3.Connection, ts_codes: list[str], *, as_of: datetime | None) -> dict[str, _DailyMetric]:
    if not ts_codes:
        return {}
    end_key = as_of.strftime("%Y%m%d") if as_of else "99999999"
    start_key = ((as_of or datetime.now()) - timedelta(days=90)).strftime("%Y%m%d")
    grouped: dict[str, list[sqlite3.Row]] = {}
    for chunk in _chunks(ts_codes, 300):
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT ts_code, date_key, data
            FROM tushare_history
            WHERE api_name = 'daily'
              AND ts_code IN ({placeholders})
              AND date_key >= ?
              AND date_key <= ?
            ORDER BY ts_code, date_key
            """,
            [*chunk, start_key, end_key],
        ).fetchall()
        for row in rows:
            grouped.setdefault(str(row["ts_code"]), []).append(row)
    return {code: metric for code, rows in grouped.items() if (metric := _metric(rows)) is not None}


def _metric(rows: list[sqlite3.Row]) -> _DailyMetric | None:
    parsed = [_daily_row(row) for row in rows]
    parsed = [item for item in parsed if item is not None]
    if len(parsed) < 2:
        return None
    return _DailyMetric(
        return_5d=_period_return(parsed, 5),
        return_20d=_period_return(parsed, 20),
        amount_ratio_5d=_amount_ratio(parsed),
    )


def _daily_row(row: sqlite3.Row) -> dict[str, float] | None:
    try:
        data = json.loads(str(row["data"]))
        close = float(data["close"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    amount = _float(data.get("amount"))
    return {"close": close, "amount": amount or 0.0}


def _period_return(rows: list[dict[str, float]], days: int) -> float | None:
    if len(rows) < 2:
        return None
    start_index = max(0, len(rows) - days - 1)
    start = rows[start_index]["close"]
    latest = rows[-1]["close"]
    return (latest - start) / start if start else None


def _amount_ratio(rows: list[dict[str, float]]) -> float | None:
    if len(rows) < 6:
        return None
    latest = rows[-1]["amount"]
    previous = [row["amount"] for row in rows[-6:-1] if row["amount"] > 0]
    if latest <= 0 or not previous:
        return None
    return latest / (sum(previous) / len(previous))


def _ranked_by_theme(
    members_by_theme: dict[str, set[str]],
    metrics: dict[str, _DailyMetric],
) -> dict[str, list[tuple[str, _DailyMetric]]]:
    result: dict[str, list[tuple[str, _DailyMetric]]] = {}
    for theme_id, members in members_by_theme.items():
        ranked = [(code, metrics[code]) for code in members if code in metrics and metrics[code].return_5d is not None]
        ranked.sort(key=lambda item: item[1].return_5d if item[1].return_5d is not None else -999, reverse=True)
        result[theme_id] = ranked
    return result


def _is_overheated(return_since_first: float | None, return_20d: float | None) -> bool:
    return (return_20d is not None and return_20d >= 0.30) or (
        return_since_first is not None and return_since_first >= 0.50
    )


def _is_confirmed(
    return_20d: float | None,
    return_since_first: float | None,
    drawdown: float | None,
    amount_ratio: float | None,
    theme: StockEvidenceThemeContext | None,
) -> bool:
    trend = (return_20d is not None and return_20d >= 0.12) or (
        return_since_first is not None and return_since_first >= 0.18
    )
    controlled_drawdown = drawdown is None or drawdown > -0.12
    strong_theme = False
    if theme is not None:
        strong_theme = theme.is_theme_leader or (
            float(getattr(theme, "quality_score", 0) or 0) >= 0.78 and not theme.is_theme_laggard
        )
    volume_ok = amount_ratio is not None and amount_ratio >= 1.5
    return trend and controlled_drawdown and (strong_theme or volume_ok)


def _is_just_confirmed(
    return_5d: float | None,
    return_since_first: float | None,
    amount_ratio: float | None,
    theme: StockEvidenceThemeContext | None,
) -> bool:
    short_return = (return_5d is not None and return_5d >= 0.05) or (
        return_since_first is not None and 0.05 <= return_since_first < 0.18
    )
    volume_ok = amount_ratio is not None and amount_ratio >= 1.3
    not_laggard = not theme.is_theme_laggard if theme else True
    return short_return and volume_ok and not_laggard


def _is_rejected(
    unique_trigger_count: int,
    return_20d: float | None,
    return_since_first: float | None,
    theme: StockEvidenceThemeContext | None,
) -> bool:
    weak_price = (return_20d is not None and return_20d < 0) or (
        return_since_first is not None and return_since_first < 0
    )
    weak_theme = theme.is_theme_laggard if theme else False
    return unique_trigger_count >= 7 and (weak_price or weak_theme)


def _latest_amount_ratio(points: list[dict[str, Any]]) -> float | None:
    for point in reversed(points):
        value = _float(point.get("amount_ratio_5d"))
        if value is not None:
            return value
    return None


def _median(values: list[float | None]) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2


def _json_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))


def _chunks(values: list[str], size: int):
    for start in range(0, len(values), size):
        yield values[start : start + size]
