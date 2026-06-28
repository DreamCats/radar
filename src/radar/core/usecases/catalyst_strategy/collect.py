from __future__ import annotations

from datetime import datetime

from radar.core.config import RadarConfig
from radar.core.messages import CatalystFeedFilters, load_catalyst_terms, list_catalyst_feed
from radar.core.storage import connect, init_db
from radar.core.usecases.catalyst_stocks import load_catalyst_stock_detector
from radar.core.usecases.catalyst_strategy.models import (
    CatalystStockContext,
    CatalystStrategyEvidence,
)


def collect_catalyst_stock_contexts(
    config: RadarConfig,
    *,
    start_time: datetime,
    end_time: datetime,
    limit: int = 200,
    max_stocks: int = 12,
) -> tuple[list[CatalystStockContext], int]:
    conn = connect(config.database_path)
    try:
        init_db(conn)
        page = list_catalyst_feed(
            conn,
            load_catalyst_terms(config),
            CatalystFeedFilters(start_time=start_time, end_time=end_time, limit=limit),
            stock_detector=load_catalyst_stock_detector(config),
        )
    finally:
        conn.close()

    by_stock: dict[str, CatalystStockContext] = {}
    seen_evidence: set[tuple[str, str]] = set()
    for item in page.items:
        evidence = CatalystStrategyEvidence(
            message_id=item.message_id,
            source=item.source,
            sender=item.sender,
            group_name=item.group_name,
            message_time=item.first_message_time,
            latest_message_time=item.latest_message_time,
            content=item.raw_content,
            matched_terms=[hit.term for hit in item.matched_terms],
            duplicate_count=item.duplicate_count,
        )
        for mention in item.stock_mentions:
            stock_key = _stock_key(mention.ts_code, mention.stock_name)
            context = by_stock.get(stock_key)
            if context is None:
                context = CatalystStockContext(
                    stock_key=stock_key,
                    ts_code=mention.ts_code,
                    stock_name=mention.stock_name,
                    first_message_time=item.first_message_time,
                    latest_message_time=item.latest_message_time,
                    evidence=[],
                )
                by_stock[stock_key] = context

            dedupe_key = (stock_key, item.message_id)
            if dedupe_key in seen_evidence:
                continue
            seen_evidence.add(dedupe_key)
            context.evidence.append(evidence)
            context.first_message_time = min(context.first_message_time, item.first_message_time)
            context.latest_message_time = max(context.latest_message_time, item.latest_message_time)

    contexts = sorted(
        by_stock.values(),
        key=lambda item: (item.latest_message_time, len(item.evidence), item.stock_key),
        reverse=True,
    )
    return contexts[:max_stocks], page.summary.total_items


def _stock_key(ts_code: str | None, stock_name: str) -> str:
    code = (ts_code or "").strip().upper()
    return code or stock_name.strip()
