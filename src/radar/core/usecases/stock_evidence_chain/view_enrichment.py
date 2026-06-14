from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from radar.core.usecases.stock_evidence_chain.view_models import (
    StockEvidenceMarketPoint,
    StockEvidenceMarketValidation,
    StockEvidenceMessage,
)


def load_current_triggers(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    max_items: int = 8,
) -> dict[str, list[StockEvidenceMessage]]:
    result: dict[str, list[StockEvidenceMessage]] = {}
    for row in rows:
        ts_code = str(row["ts_code"])
        mentions = _current_trigger_rows(
            conn,
            ts_code=ts_code,
            window_start=str(row["window_start_time"]),
            as_of=str(row["as_of_time"]),
            max_items=max_items,
        )
        result[ts_code] = [_trigger_message(item) for item in mentions]
    return result


def build_market_validation(
    current_triggers: list[StockEvidenceMessage],
    market_points: list[StockEvidenceMarketPoint],
) -> StockEvidenceMarketValidation:
    latest = market_points[-1] if market_points else None
    first_trigger = _first_trigger_time(current_triggers)
    last_trigger = _last_trigger_time(current_triggers)
    if latest is None:
        return StockEvidenceMarketValidation(
            status="no_market",
            label="缺行情验证",
            note="本地还没有可用交易日行情，先不能判断市场是否承接。",
            current_first_time=_format_time(first_trigger),
            current_last_time=_format_time(last_trigger),
        )
    if first_trigger is None:
        return StockEvidenceMarketValidation(
            status="historical_only",
            label="只验证历史证据",
            note="这版没有恢复到窗口内新增触发，市场点只能说明历史证据链的表现。",
            latest_trade_date=latest.trade_date,
        )
    latest_date = _parse_trade_date(latest.trade_date)
    trigger_date = first_trigger.date()
    if latest_date is None:
        return StockEvidenceMarketValidation(
            status="unknown",
            label="待判断",
            note="最新交易日格式异常，先不要用它判断本次触发。",
            latest_trade_date=latest.trade_date,
            current_first_time=_format_time(first_trigger),
            current_last_time=_format_time(last_trigger),
        )
    if latest_date < trigger_date:
        return StockEvidenceMarketValidation(
            status="pending_current_trigger",
            label="本次触发待验证",
            note=(
                f"最新行情停在 {_format_trade_date(latest.trade_date)}，早于本次触发 "
                f"{first_trigger:%Y-%m-%d}，不能用它验证这批消息。"
            ),
            latest_trade_date=latest.trade_date,
            current_first_time=_format_time(first_trigger),
            current_last_time=_format_time(last_trigger),
        )
    if latest_date == trigger_date:
        return StockEvidenceMarketValidation(
            status="same_day_current_trigger",
            label="同日反馈待拆分",
            note="消息和最新交易日在同一天，只能说明同日出现，不能证明消息领先价格。",
            latest_trade_date=latest.trade_date,
            current_first_time=_format_time(first_trigger),
            current_last_time=_format_time(last_trigger),
        )
    return StockEvidenceMarketValidation(
        status="has_after_trigger_market",
        label="已有后续交易日",
        note="已经有本次触发后的交易日行情，可以继续看价格和成交是否承接。",
        latest_trade_date=latest.trade_date,
        current_first_time=_format_time(first_trigger),
        current_last_time=_format_time(last_trigger),
    )


def _current_trigger_rows(
    conn: sqlite3.Connection,
    *,
    ts_code: str,
    window_start: str,
    as_of: str,
    max_items: int,
) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT smm.*, m.raw_content
        FROM stock_message_mentions smm
        JOIN messages m ON m.message_id = smm.message_id
        WHERE smm.ts_code = ?
          AND smm.message_time >= ?
          AND smm.message_time <= ?
        ORDER BY smm.message_time ASC, smm.message_id ASC
        """,
        (ts_code, window_start, as_of),
    ).fetchall()
    selected: list[sqlite3.Row] = []
    seen: set[str] = set()
    for row in rows:
        fingerprint = str(row["fingerprint"])
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        selected.append(row)
        if len(selected) >= max_items:
            break
    return selected


def _trigger_message(row: sqlite3.Row) -> StockEvidenceMessage:
    raw_content = str(row["raw_content"] or "")
    return StockEvidenceMessage(
        message_id=str(row["message_id"]),
        time=str(row["message_time"]).replace("T", " ")[:16],
        type=_evidence_type(row),
        evidence=" ".join(raw_content.split())[:220],
        sender=str(row["sender"] or "") or None,
        group_name=str(row["group_name"] or "") or None,
        raw_content=raw_content,
    )


def _evidence_type(row: sqlite3.Row) -> str:
    families = _families(row["evidence_families_json"])
    if "catalyst" in families:
        return "本次催化"
    if "roadshow" in families:
        return "本次路演"
    if "push" in families:
        return "本次推荐"
    if "price" in families:
        return "本次价格"
    category = str(row["category"] or "")
    if category == "recommendation":
        return "本次推荐"
    if category == "research":
        return "本次研究"
    if category == "industry":
        return "本次行业"
    return "本次触发"


def _families(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _first_trigger_time(items: list[StockEvidenceMessage]) -> datetime | None:
    times = [_parse_message_time(item.time) for item in items]
    ordered = sorted(time for time in times if time is not None)
    return ordered[0] if ordered else None


def _last_trigger_time(items: list[StockEvidenceMessage]) -> datetime | None:
    times = [_parse_message_time(item.time) for item in items]
    ordered = sorted(time for time in times if time is not None)
    return ordered[-1] if ordered else None


def _parse_message_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("T", " ")
    candidates = [normalized[:19], normalized[:16]]
    for text, fmt in (
        (candidates[0], "%Y-%m-%d %H:%M:%S"),
        (candidates[1], "%Y-%m-%d %H:%M"),
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _parse_trade_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = _format_trade_date(value)
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError:
        return None


def _format_trade_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value[:10]


def _format_time(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M") if value is not None else None
