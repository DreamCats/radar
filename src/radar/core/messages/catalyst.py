from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from radar.core.config import RadarConfig
from radar.core.messages.catalyst_dedupe import cluster_dedupe_hash
from radar.core.messages.catalyst_models import (
    CatalystCategory,
    CatalystDuplicateSource,
    CatalystEvidenceMessage,
    CatalystFeedFilters,
    CatalystFeedItem,
    CatalystFeedPage,
    CatalystFeedSummary,
    CatalystStockDetector,
    CatalystStockMention,
    CatalystTermHit,
    CatalystTermLibrary,
)


_CLUSTER_GAP_SECONDS = 30


@dataclass(frozen=True)
class _MessageCluster:
    rows: tuple[sqlite3.Row, ...]

    @property
    def first_row(self) -> sqlite3.Row:
        return self.rows[0]

    @property
    def latest_row(self) -> sqlite3.Row:
        return self.rows[-1]

    @property
    def first_time(self) -> datetime:
        return datetime.fromisoformat(self.first_row["message_time"])

    @property
    def latest_time(self) -> datetime:
        return datetime.fromisoformat(self.latest_row["message_time"])

    @property
    def raw_content(self) -> str:
        return "\n\n".join(str(row["raw_content"]) for row in self.rows)


class _CatalystAccumulator:
    def __init__(self, *, key: str, content_hash: str, cluster: _MessageCluster) -> None:
        self.key = key
        self.content_hash = content_hash
        self.first_cluster = cluster
        self.latest_cluster = cluster
        self.hit_map: dict[tuple[str, str], CatalystTermHit] = {}
        self.stock_map: dict[tuple[str | None, str], CatalystStockMention] = {}
        self.sources: list[CatalystDuplicateSource] = []
        self.message_count = len(cluster.rows)
        self.first_cluster_message_hits: dict[str, list[CatalystTermHit]] = {}

    def add(
        self,
        cluster: _MessageCluster,
        message_hits: dict[str, list[CatalystTermHit]],
        stock_mentions: list[CatalystStockMention],
    ) -> None:
        if not self.sources or cluster.first_time < self.first_cluster.first_time:
            self.first_cluster = cluster
            self.first_cluster_message_hits = message_hits
        if cluster.latest_time > self.latest_cluster.latest_time:
            self.latest_cluster = cluster
        hits = _flatten_message_hits(message_hits)
        for hit in hits:
            self.hit_map.setdefault((hit.category_id, hit.term), hit)
        for mention in stock_mentions:
            self.stock_map.setdefault((mention.ts_code, mention.stock_name), mention)
        self.sources.append(
            CatalystDuplicateSource(
                message_id=cluster.first_row["message_id"],
                source=cluster.first_row["source"],
                sender=cluster.first_row["sender"],
                group_name=cluster.first_row["group_name"],
                message_time=cluster.first_time,
                latest_message_time=cluster.latest_time,
                message_count=len(cluster.rows),
            )
        )

    def to_item(self) -> CatalystFeedItem:
        return CatalystFeedItem(
            key=self.key,
            message_id=self.first_cluster.first_row["message_id"],
            source=self.first_cluster.first_row["source"],
            sender=self.first_cluster.first_row["sender"],
            group_name=self.first_cluster.first_row["group_name"],
            first_message_time=self.first_cluster.first_time,
            latest_message_time=self.latest_cluster.latest_time,
            raw_content=self.first_cluster.raw_content,
            normalized_content_hash=self.content_hash,
            message_count=self.message_count,
            messages=[
                CatalystEvidenceMessage(
                    message_id=row["message_id"],
                    message_time=datetime.fromisoformat(row["message_time"]),
                    raw_content=row["raw_content"],
                    matched_terms=self.first_cluster_message_hits.get(row["message_id"], []),
                )
                for row in self.first_cluster.rows
            ],
            matched_terms=list(self.hit_map.values()),
            stock_mentions=list(self.stock_map.values()),
            duplicate_count=len(self.sources),
            duplicate_sources=sorted(self.sources, key=lambda item: item.message_time),
        )


def load_catalyst_terms(config: RadarConfig) -> CatalystTermLibrary:
    """读取个人词库；不存在时回退仓库默认模板。"""

    personal_path = catalyst_terms_path(config)
    path = personal_path if personal_path.exists() else default_catalyst_terms_path()
    return _read_terms(path)


def save_catalyst_terms(config: RadarConfig, library: CatalystTermLibrary) -> CatalystTermLibrary:
    path = catalyst_terms_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = library.model_dump()
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return library


def reset_catalyst_terms(config: RadarConfig) -> CatalystTermLibrary:
    path = catalyst_terms_path(config)
    if path.exists():
        path.unlink()
    return load_catalyst_terms(config)


def catalyst_terms_path(config: RadarConfig) -> Path:
    return config.config_dir / "catalyst_terms.yaml"


def default_catalyst_terms_path() -> Path:
    return Path(__file__).resolve().parents[4] / "data" / "catalyst_terms" / "default.yaml"


def list_catalyst_feed(
    conn: sqlite3.Connection,
    library: CatalystTermLibrary,
    filters: CatalystFeedFilters,
    *,
    stock_detector: CatalystStockDetector | None = None,
) -> CatalystFeedPage:
    if filters.start_time > filters.end_time:
        raise ValueError("start_time 不能晚于 end_time")

    selected_category_ids = set(filters.category_ids)
    rows = _query_candidate_messages(conn, filters)
    stock_mentions = _stock_mentions_by_message_id(conn, [row["message_id"] for row in rows])
    accumulators: dict[str, _CatalystAccumulator] = {}

    for cluster in _cluster_messages(rows):
        if filters.keyword and not _contains_term(cluster.raw_content, filters.keyword):
            continue
        message_hits = _match_cluster_messages(cluster, library.categories)
        hits = _flatten_message_hits(message_hits)
        if not hits:
            continue

        content_hash = cluster_dedupe_hash([str(row["raw_content"]) for row in cluster.rows])
        key = content_hash if filters.dedupe else cluster.first_row["message_id"]
        accumulator = accumulators.get(key)
        if accumulator is None:
            accumulator = _CatalystAccumulator(key=key, content_hash=content_hash, cluster=cluster)
            accumulators[key] = accumulator
        accumulator.add(cluster, message_hits, _stock_mentions_for_cluster(cluster, stock_mentions, stock_detector))

    items = [item for item in (accumulator.to_item() for accumulator in accumulators.values()) if item.stock_mentions]
    items.sort(key=lambda item: (item.latest_message_time, item.key), reverse=True)
    summary = _feed_summary(items)
    filtered_items = _filter_items_by_category(items, selected_category_ids)
    summary = _feed_summary(
        filtered_items,
        category_counts=summary.category_counts,
        term_counts=summary.term_counts,
        available_total_items=len(items),
    )
    page_items = _apply_cursor(filtered_items, filters)
    has_more = len(page_items) > filters.limit
    page_items = page_items[: filters.limit]
    if not has_more or not page_items:
        return CatalystFeedPage(items=page_items, summary=summary)

    last = page_items[-1]
    return CatalystFeedPage(
        items=page_items,
        summary=summary,
        next_cursor_time=last.latest_message_time,
        next_cursor_key=last.key,
    )


def _read_terms(path: Path) -> CatalystTermLibrary:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return CatalystTermLibrary(categories=[])
    if not isinstance(data, dict):
        raise ValueError(f"催化词配置根节点必须是 mapping: {path}")
    return CatalystTermLibrary(**data)


def _query_candidate_messages(
    conn: sqlite3.Connection,
    filters: CatalystFeedFilters,
) -> list[sqlite3.Row]:
    where = ["m.message_time >= ?", "m.message_time <= ?"]
    params: list[object] = [filters.start_time.isoformat(), filters.end_time.isoformat()]
    if filters.source:
        where.append("m.source = ?")
        params.append(filters.source)
    if filters.group_name:
        if filters.source == "个人消息":
            where.append("m.sender = ?")
            params.append(filters.group_name)
        elif filters.source == "个人群":
            where.append("m.group_name = ?")
            params.append(filters.group_name)
        else:
            where.append(
                "((m.source = '个人群' AND m.group_name = ?) OR "
                "(m.source = '个人消息' AND m.sender = ?))"
            )
            params.extend([filters.group_name, filters.group_name])

    return conn.execute(
        f"""
        SELECT m.*
        FROM messages m
        WHERE {" AND ".join(where)}
        ORDER BY m.message_time ASC, m.message_id ASC
        """,
        params,
    ).fetchall()


def _match_terms(content: str, categories: list[CatalystCategory]) -> list[CatalystTermHit]:
    hits: list[CatalystTermHit] = []
    for category in categories:
        for term in category.terms:
            if _contains_term(content, term):
                hits.append(
                    CatalystTermHit(
                        category_id=category.id,
                        category_name=category.name,
                        color=category.color,
                        term=term,
                    )
                )
    return hits


def _match_cluster_messages(
    cluster: _MessageCluster,
    categories: list[CatalystCategory],
) -> dict[str, list[CatalystTermHit]]:
    message_hits: dict[str, list[CatalystTermHit]] = {}
    for row in cluster.rows:
        hits = _match_terms(str(row["raw_content"]), categories)
        if hits:
            message_hits[row["message_id"]] = hits
    return message_hits


def _flatten_message_hits(message_hits: dict[str, list[CatalystTermHit]]) -> list[CatalystTermHit]:
    hit_map: dict[tuple[str, str], CatalystTermHit] = {}
    for hits in message_hits.values():
        for hit in hits:
            hit_map.setdefault((hit.category_id, hit.term), hit)
    return list(hit_map.values())


def _contains_term(content: str, term: str) -> bool:
    stripped = term.strip()
    if not stripped:
        return False
    if stripped.isascii() and any(char.isalnum() for char in stripped):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(stripped)}(?![A-Za-z0-9])"
        return re.search(pattern, content, flags=re.IGNORECASE) is not None
    return stripped.lower() in content.lower()


def _cluster_messages(rows: list[sqlite3.Row]) -> list[_MessageCluster]:
    clusters: list[_MessageCluster] = []
    groups: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault(_conversation_cluster_key(row), []).append(row)

    for group_rows in groups.values():
        group_rows.sort(key=lambda row: (row["message_time"], row["message_id"]))
        current: list[sqlite3.Row] = []
        previous_time: datetime | None = None
        for row in group_rows:
            message_time = datetime.fromisoformat(row["message_time"])
            if previous_time is None or (message_time - previous_time).total_seconds() <= _CLUSTER_GAP_SECONDS:
                current.append(row)
            else:
                clusters.append(_MessageCluster(tuple(current)))
                current = [row]
            previous_time = message_time
        if current:
            clusters.append(_MessageCluster(tuple(current)))

    clusters.sort(key=lambda cluster: (cluster.first_time, cluster.first_row["message_id"]))
    return clusters


def _conversation_cluster_key(row: sqlite3.Row) -> tuple[str, str, str]:
    if row["source"] == "个人消息":
        conversation = row["sender"]
    else:
        conversation = row["group_name"] or ""
    return (row["source"], conversation, row["sender"])


def _stock_mentions_by_message_id(
    conn: sqlite3.Connection,
    message_ids: list[str],
) -> dict[str, list[CatalystStockMention]]:
    if not message_ids or not _table_exists(conn, "analyst_stock_mentions"):
        return {}
    result: dict[str, list[CatalystStockMention]] = {}
    for start in range(0, len(message_ids), 500):
        chunk = message_ids[start : start + 500]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT message_id, ts_code, stock_name
            FROM analyst_stock_mentions
            WHERE message_id IN ({placeholders})
            ORDER BY message_time DESC
            """,
            chunk,
        ).fetchall()
        for row in rows:
            result.setdefault(row["message_id"], []).append(
                CatalystStockMention(ts_code=row["ts_code"], stock_name=row["stock_name"])
            )
    return result


def _stock_mentions_for_row(
    row: sqlite3.Row,
    mentions_by_message_id: dict[str, list[CatalystStockMention]],
    stock_detector: CatalystStockDetector | None = None,
) -> list[CatalystStockMention]:
    mentions = list(mentions_by_message_id.get(row["message_id"], []))
    seen = {(mention.ts_code, mention.stock_name) for mention in mentions}
    seen_codes = {mention.ts_code for mention in mentions if mention.ts_code}
    if stock_detector is not None:
        for mention in stock_detector(row["raw_content"]):
            key = (mention.ts_code, mention.stock_name)
            if key not in seen:
                seen.add(key)
                if mention.ts_code:
                    seen_codes.add(mention.ts_code)
                mentions.append(mention)
    for code in _stock_codes(row["raw_content"]):
        if code in seen_codes:
            continue
        mention = CatalystStockMention(ts_code=code, stock_name=code)
        key = (mention.ts_code, mention.stock_name)
        if key not in seen:
            seen.add(key)
            seen_codes.add(code)
            mentions.append(mention)
    return mentions


def _stock_mentions_for_cluster(
    cluster: _MessageCluster,
    mentions_by_message_id: dict[str, list[CatalystStockMention]],
    stock_detector: CatalystStockDetector | None = None,
) -> list[CatalystStockMention]:
    mentions: list[CatalystStockMention] = []
    seen: set[tuple[str | None, str]] = set()
    for row in cluster.rows:
        for mention in _stock_mentions_for_row(row, mentions_by_message_id, stock_detector):
            key = (mention.ts_code, mention.stock_name)
            if key in seen:
                continue
            seen.add(key)
            mentions.append(mention)
    return mentions


def _stock_codes(content: str) -> list[str]:
    codes: list[str] = []
    for match in re.finditer(r"(?<!\d)([03468]\d{5})(?:\.(SH|SZ|BJ))?(?!\d)", content, re.I):
        symbol = match.group(1)
        suffix = match.group(2)
        if not suffix:
            suffix = _stock_suffix(symbol)
        code = f"{symbol}.{suffix.upper()}" if suffix else symbol
        if code not in codes:
            codes.append(code)
    return codes


def _stock_suffix(symbol: str) -> str | None:
    if symbol.startswith("6"):
        return "SH"
    if symbol.startswith(("0", "3")):
        return "SZ"
    if symbol.startswith(("4", "8")):
        return "BJ"
    return None


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _apply_cursor(
    items: list[CatalystFeedItem],
    filters: CatalystFeedFilters,
) -> list[CatalystFeedItem]:
    if not filters.cursor_time or not filters.cursor_key:
        return items[: filters.limit + 1]
    return [
        item
        for item in items
        if (item.latest_message_time, item.key) < (filters.cursor_time, filters.cursor_key)
    ][: filters.limit + 1]


def _filter_items_by_category(
    items: list[CatalystFeedItem],
    category_ids: set[str],
) -> list[CatalystFeedItem]:
    if not category_ids:
        return items
    return [
        item
        for item in items
        if any(hit.category_id in category_ids for hit in item.matched_terms)
    ]


def _feed_summary(
    items: list[CatalystFeedItem],
    *,
    category_counts: dict[str, int] | None = None,
    term_counts: dict[str, dict[str, int]] | None = None,
    available_total_items: int | None = None,
) -> CatalystFeedSummary:
    summary_category_counts: dict[str, int] = dict(category_counts or {})
    summary_term_counts: dict[str, dict[str, int]] = {
        category_id: dict(counts)
        for category_id, counts in (term_counts or {}).items()
    }
    total_messages = 0
    for item in items:
        total_messages += sum(source.message_count for source in item.duplicate_sources)
        if category_counts is None:
            for category_id in {hit.category_id for hit in item.matched_terms}:
                summary_category_counts[category_id] = summary_category_counts.get(category_id, 0) + 1
        if term_counts is None:
            for category_id, term in {(hit.category_id, hit.term) for hit in item.matched_terms}:
                category_term_counts = summary_term_counts.setdefault(category_id, {})
                category_term_counts[term] = category_term_counts.get(term, 0) + 1
    return CatalystFeedSummary(
        total_items=len(items),
        total_messages=total_messages,
        duplicate_messages=max(0, total_messages - len(items)),
        available_total_items=available_total_items if available_total_items is not None else len(items),
        category_counts=summary_category_counts,
        term_counts=summary_term_counts,
    )
