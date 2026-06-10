from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.store import connect, init_db
from radar.core.usecases.stock_evidence_chain.llm import judge_pack, load_reusable_judgement, save_judgement
from radar.core.usecases.stock_evidence_chain.market import load_market_evidence
from radar.core.usecases.stock_evidence_chain.matcher import (
    StockMatcher,
    content_fingerprint,
    evidence_features,
    load_stocks,
)
from radar.core.usecases.stock_evidence_chain.storage import (
    delete_mentions_for_messages,
    load_candidates,
    load_evidence_pack,
    load_messages,
    mark_indexed,
    save_candidates,
    upsert_mentions,
)
from radar.core.usecases.stock_evidence_chain.models import EvidencePack, StockMention

MATCHER_VERSION = "stock-evidence-v2"


@dataclass(frozen=True)
class MentionIndexResult:
    scanned_messages: int
    mention_count: int
    changed_count: int


@dataclass(frozen=True)
class EvidenceChainRunResult:
    as_of: datetime
    window_start: datetime
    evidence_start: datetime
    indexed_messages: int
    mention_count: int
    candidate_count: int
    judged_count: int
    reused_count: int
    failed_count: int


def index_stock_mentions(
    config: RadarConfig,
    *,
    start: datetime,
    end: datetime,
) -> MentionIndexResult:
    conn = connect(config.database_path)
    market_conn = connect(config.market_database_path)
    try:
        init_db(conn)
        migrate_market_db(market_conn)
        stocks = load_stocks(market_conn)
        matcher = StockMatcher(stocks)
        messages = load_messages(
            conn,
            start=start,
            end=end,
            blacklist_patterns=config.filters.group_blacklist_patterns,
            matcher_version=MATCHER_VERSION,
        )
        mentions = _mentions_for_messages(messages, matcher)
        delete_mentions_for_messages(conn, messages)
        changed = upsert_mentions(conn, mentions)
        mark_indexed(
            conn,
            messages=messages,
            mention_counts=_mention_counts(mentions),
            matcher_version=MATCHER_VERSION,
        )
        return MentionIndexResult(len(messages), len(mentions), changed)
    finally:
        conn.close()
        market_conn.close()


def build_stock_evidence_chain(
    config: RadarConfig,
    *,
    as_of: datetime | None = None,
    window_start: datetime | None = None,
    evidence_days: int = 40,
    limit: int = 120,
    run_llm: bool = False,
    llm_workers: int = 16,
    llm_providers: list[str | None] | None = None,
    llm_model: str | None = None,
    llm_max_tokens: int = 2048,
    llm_temperature: float = 0.2,
    force_llm: bool = False,
) -> EvidenceChainRunResult:
    conn = connect(config.database_path)
    market_conn = connect(config.market_database_path)
    try:
        init_db(conn)
        migrate_market_db(market_conn)
        as_of = as_of or _latest_message_time(conn)
        window_start = window_start or _previous_close(as_of)
        evidence_start = as_of - timedelta(days=evidence_days)
        indexed = index_stock_mentions(config, start=evidence_start, end=as_of)
        candidates = load_candidates(conn, window_start=window_start, as_of=as_of)[:limit]
        save_candidates(conn, as_of=as_of, window_start=window_start, evidence_start=evidence_start, candidates=candidates)
        judged, reused, failed = 0, 0, 0
        if run_llm and candidates:
            packs = []
            for item in candidates:
                pack = load_evidence_pack(conn, candidate=item, evidence_start=evidence_start, as_of=as_of, max_items=80)
                market = load_market_evidence(
                    config,
                    market_conn,
                    ts_code=item.stock.ts_code,
                    evidence=pack.evidence,
                    evidence_start=evidence_start,
                    as_of=as_of,
                )
                packs.append(EvidencePack(candidate=pack.candidate, evidence=pack.evidence, market=market))
            judged, reused, failed = _judge_packs(
                config,
                conn,
                packs=packs,
                as_of=as_of,
                window_start=window_start,
                evidence_start=evidence_start,
                providers=llm_providers or [None],
                model=llm_model,
                max_tokens=llm_max_tokens,
                temperature=llm_temperature,
                workers=llm_workers,
                force_llm=force_llm,
            )
        return EvidenceChainRunResult(
            as_of=as_of,
            window_start=window_start,
            evidence_start=evidence_start,
            indexed_messages=indexed.scanned_messages,
            mention_count=indexed.mention_count,
            candidate_count=len(candidates),
            judged_count=judged,
            reused_count=reused,
            failed_count=failed,
        )
    finally:
        conn.close()
        market_conn.close()


def _mentions_for_messages(messages, matcher: StockMatcher) -> list[StockMention]:
    mentions: list[StockMention] = []
    for message in messages:
        fingerprint = content_fingerprint(message.raw_content)
        for stock in matcher.detect(message.raw_content, strict=True):
            families, score = evidence_features(message, stock)
            mentions.append(
                StockMention(
                    stock=stock,
                    message=message,
                    fingerprint=fingerprint,
                    evidence_families=families,
                    evidence_score=score,
                )
            )
    return mentions


def _mention_counts(mentions: list[StockMention]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for mention in mentions:
        message_id = mention.message.message_id
        counts[message_id] = counts.get(message_id, 0) + 1
    return counts


def _judge_packs(
    config: RadarConfig,
    conn,
    *,
    packs,
    as_of: datetime,
    window_start: datetime,
    evidence_start: datetime,
    providers: list[str | None],
    model: str | None,
    max_tokens: int,
    temperature: float,
    workers: int,
    force_llm: bool,
) -> tuple[int, int, int]:
    judged = 0
    reused = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        futures = {}
        for index, pack in enumerate(packs):
            reusable = None if force_llm else load_reusable_judgement(conn, pack=pack)
            if reusable is not None:
                save_judgement(
                    conn,
                    as_of=as_of,
                    window_start=window_start,
                    evidence_start=evidence_start,
                    pack=pack,
                    judgement=reusable,
                )
                reused += 1
                continue
            provider = providers[index % len(providers)]
            future = pool.submit(
                judge_pack,
                config,
                pack,
                provider_name=provider,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            futures[future] = pack
        for future in as_completed(futures):
            pack = futures[future]
            try:
                judgement = future.result()
                save_judgement(
                    conn,
                    as_of=as_of,
                    window_start=window_start,
                    evidence_start=evidence_start,
                    pack=pack,
                    judgement=judgement,
                )
                judged += 1
            except Exception:
                failed += 1
    return judged, reused, failed


def _latest_message_time(conn) -> datetime:
    value = conn.execute("SELECT MAX(message_time) FROM messages").fetchone()[0]
    if not value:
        raise ValueError("messages 为空，无法生成证据链")
    return datetime.fromisoformat(str(value))


def _previous_close(as_of: datetime) -> datetime:
    return datetime.combine(as_of.date() - timedelta(days=1), time(15, 0))
