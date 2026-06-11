from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from pydantic import BaseModel

from radar.core.config import RadarConfig
from radar.core.storage.db import migrate_market_db
from radar.core.market.anchors import refresh_market_anchor_derivatives
from radar.core.market.theme_rules import ThemeNormalization, normalize_theme_anchor


class RefreshMarketThemeNormalizationResult(BaseModel):
    latest_trade_date: str | None = None
    theme_count: int = 0
    source_link_count: int = 0
    membership_count: int = 0
    current_stock_count: int = 0
    covered_stock_count: int = 0
    coverage_ratio: float = 0.0
    ambiguous_stock_count: int = 0


@dataclass
class _ThemeNode:
    theme_id: str
    theme_name: str
    theme_type: str
    aliases: set[str] = field(default_factory=set)
    first_seen_date: str = ""
    last_seen_date: str = ""


@dataclass
class _SourceLink:
    theme_id: str
    source: str
    source_code: str
    source_name: str
    source_anchor_type: str
    confidence: float
    first_seen_date: str
    last_seen_date: str


@dataclass
class _Membership:
    theme_id: str
    ts_code: str
    stock_name: str
    first_seen_date: str
    last_seen_date: str
    latest_trade_date: str
    seen_days: int = 0
    sources: dict[str, dict[str, str]] = field(default_factory=dict)
    reasons: set[str] = field(default_factory=set)


def refresh_market_theme_normalization(
    config: RadarConfig,
    *,
    rebuild_anchor_derivatives: bool = True,
) -> RefreshMarketThemeNormalizationResult:
    """基于 market anchor 派生表自动生成主题归一化层，不依赖人工纠偏。"""

    if rebuild_anchor_derivatives:
        refresh_market_anchor_derivatives(config)

    with _connect(config) as conn:
        return rebuild_market_theme_normalization_from_conn(conn)


def rebuild_market_theme_normalization_from_conn(
    conn: sqlite3.Connection,
    *,
    commit: bool = True,
) -> RefreshMarketThemeNormalizationResult:
    now = datetime.now().isoformat(timespec="seconds")
    rows = conn.execute(
        """
        SELECT anchor_key, anchor_type, anchor_name, anchor_source, source_code,
               member_source, ts_code, stock_name, first_seen_date, last_seen_date,
               seen_days, latest_reason
        FROM market_anchor_member_spans
        WHERE anchor_name <> '' AND ts_code <> ''
        """
    ).fetchall()

    nodes: dict[str, _ThemeNode] = {}
    links: dict[tuple[str, str, str, str], _SourceLink] = {}
    memberships: dict[tuple[str, str], _Membership] = {}

    for row in rows:
        normalized = normalize_theme_anchor(
            str(row["anchor_name"]),
            str(row["anchor_type"]),
            str(row["latest_reason"] or ""),
        )
        if normalized is None or not normalized.theme_key:
            continue
        theme_id = _theme_id(normalized.theme_key)
        _add_node(nodes, theme_id, row, normalized)
        _add_source_link(links, theme_id, row)
        _add_membership(memberships, theme_id, row)

    conn.execute("DELETE FROM theme_nodes")
    conn.execute("DELETE FROM theme_source_links")
    conn.execute("DELETE FROM stock_theme_memberships")
    _insert_nodes(conn, nodes.values(), now)
    _insert_links(conn, links.values(), now)
    _insert_memberships(conn, memberships.values(), now)
    if commit:
        conn.commit()

    return _summarize(conn)


def _connect(config: RadarConfig) -> sqlite3.Connection:
    config.market_database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.market_database_path)
    conn.row_factory = sqlite3.Row
    migrate_market_db(conn)
    return conn


def _add_node(
    nodes: dict[str, _ThemeNode],
    theme_id: str,
    row: sqlite3.Row,
    normalized: ThemeNormalization,
) -> None:
    name = normalized.theme_name
    node = nodes.get(theme_id)
    if node is None:
        nodes[theme_id] = _ThemeNode(
            theme_id=theme_id,
            theme_name=name,
            theme_type=normalized.theme_type,
            aliases=set(normalized.aliases),
            first_seen_date=str(row["first_seen_date"]),
            last_seen_date=str(row["last_seen_date"]),
        )
        return

    node.aliases.update(normalized.aliases)
    node.theme_type = _preferred_theme_type(node.theme_type, normalized.theme_type)
    if str(row["last_seen_date"]) >= node.last_seen_date:
        node.theme_name = name
        node.last_seen_date = str(row["last_seen_date"])
    if str(row["first_seen_date"]) < node.first_seen_date:
        node.first_seen_date = str(row["first_seen_date"])


def _add_source_link(
    links: dict[tuple[str, str, str, str], _SourceLink],
    theme_id: str,
    row: sqlite3.Row,
) -> None:
    key = (str(row["anchor_source"]), str(row["source_code"]), str(row["anchor_type"]), theme_id)
    existing = links.get(key)
    if existing is None:
        links[key] = _SourceLink(
            theme_id=theme_id,
            source=str(row["anchor_source"]),
            source_code=str(row["source_code"]),
            source_name=str(row["anchor_name"]),
            source_anchor_type=str(row["anchor_type"]),
            confidence=1.0,
            first_seen_date=str(row["first_seen_date"]),
            last_seen_date=str(row["last_seen_date"]),
        )
        return
    existing.first_seen_date = min(existing.first_seen_date, str(row["first_seen_date"]))
    existing.last_seen_date = max(existing.last_seen_date, str(row["last_seen_date"]))


def _add_membership(
    memberships: dict[tuple[str, str], _Membership],
    theme_id: str,
    row: sqlite3.Row,
) -> None:
    key = (theme_id, str(row["ts_code"]))
    source_key = f"{row['anchor_source']}:{row['source_code']}:{row['member_source']}"
    reason = _reason_text(row)
    existing = memberships.get(key)
    if existing is None:
        existing = _Membership(
            theme_id=theme_id,
            ts_code=str(row["ts_code"]),
            stock_name=str(row["stock_name"]),
            first_seen_date=str(row["first_seen_date"]),
            last_seen_date=str(row["last_seen_date"]),
            latest_trade_date=str(row["last_seen_date"]),
            seen_days=int(row["seen_days"] or 0),
        )
        memberships[key] = existing
    else:
        if str(row["last_seen_date"]) >= existing.last_seen_date:
            existing.stock_name = str(row["stock_name"])
        existing.first_seen_date = min(existing.first_seen_date, str(row["first_seen_date"]))
        existing.last_seen_date = max(existing.last_seen_date, str(row["last_seen_date"]))
        existing.latest_trade_date = max(existing.latest_trade_date, str(row["last_seen_date"]))
        existing.seen_days += int(row["seen_days"] or 0)

    existing.sources[source_key] = {
        "anchor_source": str(row["anchor_source"]),
        "source_code": str(row["source_code"]),
        "anchor_name": str(row["anchor_name"]),
        "anchor_type": str(row["anchor_type"]),
        "member_source": str(row["member_source"]),
    }
    if reason:
        existing.reasons.add(reason)


def _insert_nodes(conn: sqlite3.Connection, nodes: Iterable[_ThemeNode], now: str) -> None:
    conn.executemany(
        """
        INSERT INTO theme_nodes (
            theme_id, theme_name, theme_type, parent_theme_id, aliases_json,
            policy_tags_json, status, created_at, updated_at
        ) VALUES (?, ?, ?, NULL, ?, '[]', 'active', ?, ?)
        """,
        [
            (
                node.theme_id,
                node.theme_name,
                node.theme_type,
                json.dumps(sorted(node.aliases), ensure_ascii=False),
                now,
                now,
            )
            for node in sorted(nodes, key=lambda item: item.theme_id)
        ],
    )


def _insert_links(conn: sqlite3.Connection, links: Iterable[_SourceLink], now: str) -> None:
    conn.executemany(
        """
        INSERT INTO theme_source_links (
            theme_id, source, source_code, source_name, source_anchor_type,
            confidence, first_seen_date, last_seen_date, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                link.theme_id,
                link.source,
                link.source_code,
                link.source_name,
                link.source_anchor_type,
                link.confidence,
                link.first_seen_date,
                link.last_seen_date,
                now,
            )
            for link in sorted(links, key=lambda item: (item.theme_id, item.source, item.source_code))
        ],
    )


def _insert_memberships(conn: sqlite3.Connection, memberships: Iterable[_Membership], now: str) -> None:
    conn.executemany(
        """
        INSERT INTO stock_theme_memberships (
            theme_id, ts_code, stock_name, role, confidence, source_count,
            sources_json, reasons_json, first_seen_date, last_seen_date,
            latest_trade_date, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.theme_id,
                item.ts_code,
                item.stock_name,
                _auto_role(item),
                _auto_confidence(item),
                len(item.sources),
                json.dumps(list(item.sources.values()), ensure_ascii=False),
                json.dumps(sorted(item.reasons), ensure_ascii=False),
                item.first_seen_date,
                item.last_seen_date,
                item.latest_trade_date,
                now,
            )
            for item in sorted(memberships, key=lambda value: (value.theme_id, value.ts_code))
        ],
    )


def _summarize(conn: sqlite3.Connection) -> RefreshMarketThemeNormalizationResult:
    latest_row = conn.execute("SELECT MAX(latest_trade_date) FROM stock_theme_memberships").fetchone()
    theme_count = int(conn.execute("SELECT COUNT(*) FROM theme_nodes").fetchone()[0])
    source_link_count = int(conn.execute("SELECT COUNT(*) FROM theme_source_links").fetchone()[0])
    membership_count = int(conn.execute("SELECT COUNT(*) FROM stock_theme_memberships").fetchone()[0])
    current_stock_count = int(conn.execute("SELECT COUNT(DISTINCT ts_code) FROM market_anchor_current_members").fetchone()[0])
    covered_stock_count = int(conn.execute("SELECT COUNT(DISTINCT ts_code) FROM stock_theme_memberships").fetchone()[0])
    ambiguous_stock_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT ts_code
                FROM stock_theme_memberships
                GROUP BY ts_code
                HAVING COUNT(*) >= 12
            )
            """
        ).fetchone()[0]
    )
    return RefreshMarketThemeNormalizationResult(
        latest_trade_date=str(latest_row[0]) if latest_row and latest_row[0] else None,
        theme_count=theme_count,
        source_link_count=source_link_count,
        membership_count=membership_count,
        current_stock_count=current_stock_count,
        covered_stock_count=covered_stock_count,
        coverage_ratio=(covered_stock_count / current_stock_count if current_stock_count else 0.0),
        ambiguous_stock_count=ambiguous_stock_count,
    )


def _theme_id(theme_key: str) -> str:
    digest = hashlib.sha1(theme_key.encode("utf-8")).hexdigest()[:12]
    return f"theme:auto:{digest}"


def _preferred_theme_type(existing: str, incoming: str) -> str:
    priority = {"theme": 3, "concept": 2, "industry": 1, "stock": 0}
    return incoming if priority.get(incoming, 0) > priority.get(existing, 0) else existing


def _reason_text(row: sqlite3.Row) -> str:
    reason = str(row["latest_reason"] or "").strip()
    prefix = f"{row['anchor_source']}:{row['anchor_name']}"
    return f"{prefix}: {reason}" if reason else prefix


def _auto_role(item: _Membership) -> str:
    if len(item.sources) >= 3:
        return "core"
    if len(item.sources) >= 2:
        return "elastic"
    return "unknown"


def _auto_confidence(item: _Membership) -> float:
    source_part = min(len(item.sources), 3) * 0.12
    duration_part = min(item.seen_days, 20) * 0.01
    return round(min(0.95, 0.48 + source_part + duration_part), 2)
