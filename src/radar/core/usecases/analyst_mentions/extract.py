from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from typing import Any

from radar.core.models import MessageSource
from radar.core.usecases.analyst_mentions.identity import (
    analyst_identity,
    mention_id,
    source_candidate,
)
from radar.core.usecases.analyst_mentions.models import (
    DEFAULT_BROAD_LIST_STOCK_THRESHOLD,
    QUALITY_FLAG_BROAD_LIST,
    AnalystMentionEvent,
)
from radar.core.usecases.stock_evidence_chain.matcher import StockMatcher, content_fingerprint

HIGH_VALUE_CATEGORIES = ("research", "recommendation", "event", "industry")
_SNIPPET_LIMIT = 360
_SEGMENT_SPLIT_RE = re.compile(r"[\n\r。；;!?！？]")
_TOP_LEVEL_SECTION_RE = re.compile(r"^(?:\d+[、.．)]|[一二三四五六七八九十]+[、.．)]|【.+】|\[.+\])")
_SUBPOINT_RE = re.compile(r"^[A-Za-z][.．、)]")
_BROKER_SOURCE_PREFIX_RE = re.compile(r"^[#【\[\(（「《\s]*{name}[\s:：丨|｜\-—]")
_BROKER_SOURCE_NAMES = {
    "东北证券",
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
    "国盛证券",
    "华福证券",
    "东吴证券",
    "东兴证券",
    "西南证券",
    "西部证券",
    "南京证券",
    "首创证券",
    "长江证券",
    "光大证券",
    "广发证券",
    "海通证券",
}


def extract_mentions(
    conn: sqlite3.Connection,
    matcher: StockMatcher,
    *,
    start_time: datetime,
    end_time: datetime,
    source: MessageSource | None,
    extractor_version: str,
    min_classification_confidence: float,
) -> tuple[list[AnalystMentionEvent], int, int, int]:
    where = [
        "m.message_time >= ?",
        "m.message_time < ?",
        f"c.category IN ({', '.join('?' for _ in HIGH_VALUE_CATEGORIES)})",
        "c.status != 'ignored'",
        "c.confidence >= ?",
    ]
    params: list[Any] = [
        start_time.isoformat(),
        end_time.isoformat(),
        *HIGH_VALUE_CATEGORIES,
        min_classification_confidence,
    ]
    if source:
        where.append("m.source = ?")
        params.append(source)
    rows = conn.execute(
        f"""
        SELECT
            m.message_id, m.source, m.sender, m.message_time, m.raw_content, m.group_name,
            c.category, c.confidence
        FROM messages m
        JOIN message_classifications c ON c.message_id = m.message_id
        WHERE {" AND ".join(where)}
        ORDER BY m.message_time ASC, m.message_id ASC
        """,
        params,
    ).fetchall()
    now = datetime.now()
    mentions: list[AnalystMentionEvent] = []
    stock_hit_message_ids: set[str] = set()
    source_broker_filtered_count = 0
    for row in rows:
        text = str(row["raw_content"] or "")
        stocks = []
        for stock in matcher.detect(text, strict=True):
            snippet = stock_segment(text, stock.name, stock.symbol, stock.ts_code)
            if is_source_broker_mention(snippet, stock.name):
                source_broker_filtered_count += 1
                continue
            stocks.append((stock, snippet))
        if stocks:
            stock_hit_message_ids.add(str(row["message_id"]))
        stock_count = len(stocks)
        quality_flags = (
            (QUALITY_FLAG_BROAD_LIST,)
            if stock_count >= DEFAULT_BROAD_LIST_STOCK_THRESHOLD
            else ()
        )
        for stock, snippet in stocks:
            source_name = source_candidate(str(row["sender"]))
            analyst = analyst_identity(source_name)
            message_time = datetime.fromisoformat(str(row["message_time"]))
            mentions.append(
                AnalystMentionEvent(
                    mention_id=mention_id(str(row["message_id"]), stock.ts_code, extractor_version),
                    message_id=str(row["message_id"]),
                    source=str(row["source"]),
                    sender=source_name,
                    analyst_id=analyst.analyst_id,
                    analyst_display_name=analyst.display_name,
                    analyst_alias_key=analyst.alias_key,
                    group_name=str(row["group_name"]) if row["group_name"] else None,
                    category=str(row["category"]),
                    classification_confidence=float(row["confidence"] or 0),
                    ts_code=stock.ts_code,
                    stock_name=stock.name,
                    symbol=stock.symbol,
                    message_time=message_time,
                    event_date=message_time.strftime("%Y%m%d"),
                    evidence_snippet=snippet,
                    content_fingerprint=content_fingerprint(text),
                    extractor_version=extractor_version,
                    stock_count_in_message=stock_count,
                    quality_flags=quality_flags,
                    dedupe_key=f"{analyst.analyst_id}|{stock.ts_code}",
                    created_at=now,
                    updated_at=now,
                )
            )
    return mentions, len(rows), len(stock_hit_message_ids), source_broker_filtered_count


def stock_segment(text: str, stock_name: str, symbol: str, ts_code: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    segments = [segment.strip() for segment in _SEGMENT_SPLIT_RE.split(text) if segment.strip()]
    for term in (stock_name, symbol, ts_code):
        if not term:
            continue
        for index, line in enumerate(lines):
            if term in line:
                return _line_context(lines, index)
        for segment in segments:
            if term in segment:
                return " ".join(segment.split())[:_SNIPPET_LIMIT]
    return " ".join(text.split())[:_SNIPPET_LIMIT]


def _line_context(lines: list[str], index: int) -> str:
    line = lines[index]
    context = [line]
    if _should_expand_line(line):
        included_subpoint = False
        for next_line in lines[index + 1 :]:
            if _is_new_top_level_section(next_line):
                break
            if included_subpoint and _is_subpoint(next_line):
                break
            if _is_subpoint(next_line):
                included_subpoint = True
            context.append(next_line)
            if len(" ".join(context)) >= _SNIPPET_LIMIT:
                break
    return " ".join(" ".join(context).split())[:_SNIPPET_LIMIT]


def _should_expand_line(line: str) -> bool:
    compact = " ".join(line.split())
    return len(compact) <= 40 or _is_new_top_level_section(compact)


def _is_new_top_level_section(line: str) -> bool:
    return re.match(_TOP_LEVEL_SECTION_RE, line) is not None


def _is_subpoint(line: str) -> bool:
    return re.match(_SUBPOINT_RE, line) is not None


def is_source_broker_mention(snippet: str, stock_name: str) -> bool:
    if not _is_broker_source_name(stock_name):
        return False
    pattern = _BROKER_SOURCE_PREFIX_RE.pattern.format(name=re.escape(stock_name))
    return re.search(pattern, snippet) is not None


def _is_broker_source_name(stock_name: str) -> bool:
    return stock_name.endswith("证券") or stock_name in _BROKER_SOURCE_NAMES
