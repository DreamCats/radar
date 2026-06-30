from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from radar.core.messages import (
    CatalystDuplicateSource,
    CatalystFeedFilters,
    CatalystFeedItem,
    CatalystStockMention,
    CatalystTermHit,
    CatalystTermLibrary,
    list_catalyst_feed,
)
from radar.core.messages.catalyst_models import CatalystStockDetector
from radar.core.usecases.premarket_signal.concepts import (
    ConceptMember,
    load_concept_members,
    memberships_for_stock,
)
from radar.core.usecases.premarket_signal.models import (
    PremarketConceptRank,
    PremarketConcentrationItem,
    PremarketEvidence,
    PremarketSignalQuery,
    PremarketSignalResult,
    PremarketSignalSummary,
    PremarketStockRank,
    PremarketTimeBucket,
)

_PAGE_SIZE = 200
_MAX_CATALYST_ITEMS = 1200
_MAX_EVIDENCE_PER_CONCEPT = 6
_TIME_BUCKET_MINUTES = 10
_BOARD_LIMIT = 10
_WINDOW_SPLIT_RATIO = 0.5


@dataclass
class _StockAccumulator:
    stock: CatalystStockMention
    mention_count: int = 0
    people: set[str] = field(default_factory=set)
    messages: set[str] = field(default_factory=set)
    first_time: datetime | None = None
    latest_time: datetime | None = None
    term_map: dict[tuple[str, str], CatalystTermHit] = field(default_factory=dict)

    def add(self, person_key: str, source: CatalystDuplicateSource, item: CatalystFeedItem) -> None:
        self.mention_count += 1
        self.people.add(person_key)
        self.messages.add(source.message_id)
        self.first_time = source.message_time if self.first_time is None else min(self.first_time, source.message_time)
        latest = source.latest_message_time or source.message_time
        self.latest_time = latest if self.latest_time is None else max(self.latest_time, latest)
        for hit in item.matched_terms:
            self.term_map.setdefault((hit.category_id, hit.term), hit)

    def to_rank(self) -> PremarketStockRank:
        fallback_time = datetime.min
        return PremarketStockRank(
            ts_code=self.stock.ts_code,
            stock_name=self.stock.stock_name,
            mention_count=self.mention_count,
            person_count=len(self.people),
            message_count=len(self.messages),
            first_time=self.first_time or fallback_time,
            latest_time=self.latest_time or self.first_time or fallback_time,
            catalyst_terms=sorted(self.term_map.values(), key=lambda item: (item.category_name, item.term)),
        )


@dataclass
class _ConceptAccumulator:
    member: ConceptMember
    stock_map: dict[str, _StockAccumulator] = field(default_factory=dict)
    people: set[str] = field(default_factory=set)
    messages: set[str] = field(default_factory=set)
    person_stock_keys: set[tuple[str, str]] = field(default_factory=set)
    early_person_stock_keys: set[tuple[str, str]] = field(default_factory=set)
    late_person_stock_keys: set[tuple[str, str]] = field(default_factory=set)
    term_map: dict[tuple[str, str], CatalystTermHit] = field(default_factory=dict)
    evidence_map: dict[str, PremarketEvidence] = field(default_factory=dict)

    def add(
        self,
        *,
        stock_key: str,
        stock_accumulator: _StockAccumulator,
        person_key: str,
        source: CatalystDuplicateSource,
        item: CatalystFeedItem,
        split_time: datetime,
    ) -> None:
        self.stock_map.setdefault(stock_key, stock_accumulator)
        self.people.add(person_key)
        self.messages.add(source.message_id)
        person_stock_key = (person_key, stock_key)
        self.person_stock_keys.add(person_stock_key)
        if source.message_time >= split_time:
            self.late_person_stock_keys.add(person_stock_key)
        else:
            self.early_person_stock_keys.add(person_stock_key)
        for hit in item.matched_terms:
            self.term_map.setdefault((hit.category_id, hit.term), hit)
        if len(self.evidence_map) < _MAX_EVIDENCE_PER_CONCEPT:
            self.evidence_map.setdefault(
                source.message_id,
                PremarketEvidence(
                    message_id=source.message_id,
                    source=source.source,
                    sender=source.sender,
                    group_name=source.group_name,
                    message_time=source.message_time,
                    raw_content=item.raw_content,
                    matched_terms=item.matched_terms,
                    stock_mentions=item.stock_mentions,
                ),
            )

    def to_rank(self) -> PremarketConceptRank:
        stocks = sorted(
            (stock.to_rank() for stock in self.stock_map.values()),
            key=lambda stock: (stock.person_count, stock.mention_count, stock.message_count, stock.latest_time),
            reverse=True,
        )
        mention_count = sum(stock.mention_count for stock in self.stock_map.values())
        stock_count = len(self.stock_map)
        person_count = len(self.people)
        message_count = len(self.messages)
        term_count = len(self.term_map)
        early_count = len(self.early_person_stock_keys)
        late_count = len(self.late_person_stock_keys)
        score = person_count * 4 + stock_count * 2.5 + mention_count * 1.5 + message_count * 0.6 + term_count * 0.5
        return PremarketConceptRank(
            concept_code=self.member.concept_code,
            concept_name=self.member.concept_name,
            source=self.member.source,
            score=round(score, 2),
            velocity_score=round(late_count - early_count, 2),
            early_mention_count=early_count,
            late_mention_count=late_count,
            stock_count=stock_count,
            mention_count=mention_count,
            person_count=person_count,
            message_count=message_count,
            top_stocks=stocks,
            catalyst_terms=sorted(self.term_map.values(), key=lambda item: (item.category_name, item.term)),
            evidence=sorted(self.evidence_map.values(), key=lambda item: item.message_time),
        )


def build_premarket_signal(
    message_conn: sqlite3.Connection,
    *,
    market_conn: sqlite3.Connection | None,
    library: CatalystTermLibrary,
    query: PremarketSignalQuery,
    stock_detector: CatalystStockDetector | None = None,
) -> PremarketSignalResult:
    if query.start_time > query.end_time:
        raise ValueError("start_time 不能晚于 end_time")

    items = _collect_catalyst_items(
        message_conn,
        library=library,
        query=query,
        stock_detector=stock_detector,
    )
    concept_members, concept_source, concept_count = load_concept_members(market_conn)
    stock_accumulators: dict[str, _StockAccumulator] = {}
    concept_accumulators: dict[str, _ConceptAccumulator] = {}
    seen_person_stock: set[tuple[str, str]] = set()
    time_buckets = _init_time_buckets(query)
    split_time = _split_time(query)

    for item in sorted(items, key=lambda candidate: (candidate.first_message_time, candidate.key)):
        _add_bucket_value(time_buckets, item.latest_message_time, catalyst_items=1)
        for source in item.duplicate_sources:
            person_key = _person_key(source)
            for stock in item.stock_mentions:
                stock_key = _stock_key(stock)
                dedupe_key = (person_key, stock_key)
                if dedupe_key in seen_person_stock:
                    continue
                seen_person_stock.add(dedupe_key)
                _add_bucket_value(time_buckets, source.message_time, dedup_person_stock_mentions=1)
                stock_accumulator = stock_accumulators.setdefault(stock_key, _StockAccumulator(stock=stock))
                stock_accumulator.add(person_key, source, item)
                for member in memberships_for_stock(stock, concept_members):
                    concept = concept_accumulators.setdefault(
                        member.concept_code,
                        _ConceptAccumulator(member=member),
                    )
                    concept.add(
                        stock_key=stock_key,
                        stock_accumulator=stock_accumulator,
                        person_key=person_key,
                        source=source,
                        item=item,
                        split_time=split_time,
                    )

    all_rank_pairs = sorted(
        ((concept.to_rank(), concept) for concept in concept_accumulators.values()),
        key=lambda pair: (pair[0].score, pair[0].person_count, pair[0].stock_count, pair[0].mention_count),
        reverse=True,
    )
    concepts = [rank for rank, _concept in all_rank_pairs[: query.limit]]
    top_concepts = [rank for rank, _concept in all_rank_pairs[:_BOARD_LIMIT]]
    bottom_concepts = [rank for rank, _concept in reversed(all_rank_pairs[-_BOARD_LIMIT:])]
    velocity_concepts = [
        rank
        for rank, _concept in sorted(
            all_rank_pairs,
            key=lambda pair: (
                pair[0].velocity_score,
                pair[0].late_mention_count,
                pair[0].score,
                pair[0].person_count,
            ),
            reverse=True,
        )[:_BOARD_LIMIT]
    ]
    concentration = _build_concentration(all_rank_pairs, total_count=len(seen_person_stock))

    summary = PremarketSignalSummary(
        start_time=query.start_time,
        end_time=query.end_time,
        messages_scanned=_count_window_messages(message_conn, query),
        catalyst_items=len(items),
        stock_mentions=sum(len(item.stock_mentions) for item in items),
        dedup_person_stock_mentions=len(seen_person_stock),
        concept_source=concept_source,
        concept_count=concept_count,
        ranked_concept_count=len(all_rank_pairs),
    )
    return PremarketSignalResult(
        query=query,
        summary=summary,
        concepts=concepts,
        top_concepts=top_concepts,
        bottom_concepts=bottom_concepts,
        velocity_concepts=velocity_concepts,
        concentration=concentration,
        time_buckets=time_buckets,
    )


def slim_premarket_signal(result: PremarketSignalResult) -> PremarketSignalResult:
    return result.model_copy(
        update={
            "concepts": [_slim_concept(concept) for concept in result.concepts],
            "top_concepts": [_slim_concept(concept) for concept in result.top_concepts],
            "bottom_concepts": [_slim_concept(concept) for concept in result.bottom_concepts],
            "velocity_concepts": [_slim_concept(concept) for concept in result.velocity_concepts],
        }
    )


def find_premarket_concept(result: PremarketSignalResult, concept_code: str) -> PremarketConceptRank | None:
    seen: set[str] = set()
    for concept in [
        *result.top_concepts,
        *result.bottom_concepts,
        *result.velocity_concepts,
        *result.concepts,
    ]:
        if concept.concept_code in seen:
            continue
        seen.add(concept.concept_code)
        if concept.concept_code == concept_code:
            return concept
    return None


def _slim_concept(concept: PremarketConceptRank) -> PremarketConceptRank:
    return concept.model_copy(update={"top_stocks": [], "catalyst_terms": [], "evidence": []})


def _collect_catalyst_items(
    conn: sqlite3.Connection,
    *,
    library: CatalystTermLibrary,
    query: PremarketSignalQuery,
    stock_detector: CatalystStockDetector | None,
) -> list[CatalystFeedItem]:
    items: list[CatalystFeedItem] = []
    cursor_time: datetime | None = None
    cursor_key: str | None = None
    while len(items) < _MAX_CATALYST_ITEMS:
        page = list_catalyst_feed(
            conn,
            library,
            CatalystFeedFilters(
                start_time=query.start_time,
                end_time=query.end_time,
                dedupe=True,
                cursor_time=cursor_time,
                cursor_key=cursor_key,
                limit=_PAGE_SIZE,
            ),
            stock_detector=stock_detector,
        )
        items.extend(page.items)
        if not page.next_cursor_time or not page.next_cursor_key:
            break
        cursor_time = page.next_cursor_time
        cursor_key = page.next_cursor_key
    return items[:_MAX_CATALYST_ITEMS]


def _count_window_messages(conn: sqlite3.Connection, query: PremarketSignalQuery) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS message_count
        FROM messages
        WHERE message_time >= ? AND message_time <= ?
        """,
        (query.start_time.isoformat(), query.end_time.isoformat()),
    ).fetchone()
    return int(row["message_count"] if row is not None else 0)


def _init_time_buckets(query: PremarketSignalQuery) -> list[PremarketTimeBucket]:
    buckets: list[PremarketTimeBucket] = []
    cursor = query.start_time
    step = timedelta(minutes=_TIME_BUCKET_MINUTES)
    while cursor < query.end_time:
        bucket_end = min(cursor + step, query.end_time)
        buckets.append(PremarketTimeBucket(start_time=cursor, end_time=bucket_end))
        cursor = bucket_end
    return buckets or [PremarketTimeBucket(start_time=query.start_time, end_time=query.end_time)]


def _split_time(query: PremarketSignalQuery) -> datetime:
    duration = query.end_time - query.start_time
    return query.start_time + duration * _WINDOW_SPLIT_RATIO


def _add_bucket_value(
    buckets: list[PremarketTimeBucket],
    occurred_at: datetime,
    *,
    catalyst_items: int = 0,
    dedup_person_stock_mentions: int = 0,
) -> None:
    if not buckets:
        return
    target = buckets[-1]
    for bucket in buckets:
        if bucket.start_time <= occurred_at < bucket.end_time:
            target = bucket
            break
    target.catalyst_items += catalyst_items
    target.dedup_person_stock_mentions += dedup_person_stock_mentions


def _build_concentration(
    concept_rank_pairs: list[tuple[PremarketConceptRank, _ConceptAccumulator]],
    *,
    total_count: int,
) -> list[PremarketConcentrationItem]:
    total = max(1, total_count)
    items: list[PremarketConcentrationItem] = []
    for concept_count in (1, 3, 5, 10):
        covered: set[tuple[str, str]] = set()
        for _rank, concept in concept_rank_pairs[:concept_count]:
            covered.update(concept.person_stock_keys)
        covered_count = len(covered)
        items.append(
            PremarketConcentrationItem(
                concept_count=concept_count,
                covered_dedup_person_stock_mentions=covered_count,
                total_dedup_person_stock_mentions=total_count,
                coverage_pct=round(covered_count / total * 100, 1),
            )
        )
    return items


def _stock_key(stock: CatalystStockMention) -> str:
    return stock.ts_code or stock.stock_name


def _person_key(source: CatalystDuplicateSource) -> str:
    return source.sender.strip() or f"{source.source}:{source.group_name or ''}"
