from __future__ import annotations

import json
import sqlite3
from typing import Literal

from pydantic import BaseModel, Field

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.models import MessageAnchorType

AnchorTermKind = Literal["name", "alias", "stock_name"]


class AnchorTerm(BaseModel):
    anchor_id: str
    anchor_type: MessageAnchorType
    name: str
    term: str
    term_kind: AnchorTermKind
    trade_date: str
    hot_score: float | None = None
    source: str = ""


class AnchorDictionary(BaseModel):
    trade_date: str
    terms: list[AnchorTerm] = Field(default_factory=list)

    @property
    def anchor_count(self) -> int:
        return len({item.anchor_id for item in self.terms})


def load_anchor_dictionary(config: RadarConfig, *, trade_date: str) -> AnchorDictionary:
    """从 market.sqlite3 加载指定交易日 anchor 词表，股票名来自成分股表。"""

    terms: dict[tuple[str, str], AnchorTerm] = {}
    with _connect_market(config) as conn:
        for row in conn.execute(
            """
            SELECT anchor_id, anchor_type, name, aliases_json, source,
                   trade_date, hot_score
            FROM market_anchors
            WHERE trade_date = ?
            """,
            (trade_date,),
        ).fetchall():
            _add_term(
                terms,
                AnchorTerm(
                    anchor_id=row["anchor_id"],
                    anchor_type=row["anchor_type"],
                    name=row["name"],
                    term=row["name"],
                    term_kind="name",
                    trade_date=row["trade_date"],
                    hot_score=row["hot_score"],
                    source=row["source"],
                ),
            )
            for alias in _aliases(row["aliases_json"]):
                _add_term(
                    terms,
                    AnchorTerm(
                        anchor_id=row["anchor_id"],
                        anchor_type=row["anchor_type"],
                        name=row["name"],
                        term=alias,
                        term_kind="alias",
                        trade_date=row["trade_date"],
                        hot_score=row["hot_score"],
                        source=row["source"],
                    ),
                )

        for row in conn.execute(
            """
            SELECT ts_code, stock_name, trade_date, COUNT(*) AS ref_count
            FROM market_anchor_members
            WHERE trade_date = ?
            GROUP BY ts_code, stock_name, trade_date
            """,
            (trade_date,),
        ).fetchall():
            stock_name = str(row["stock_name"] or "").strip()
            ts_code = str(row["ts_code"] or "").strip()
            if not stock_name or not ts_code:
                continue
            _add_term(
                terms,
                AnchorTerm(
                    anchor_id=f"stock:{ts_code}",
                    anchor_type="stock",
                    name=stock_name,
                    term=stock_name,
                    term_kind="stock_name",
                    trade_date=row["trade_date"],
                    hot_score=float(row["ref_count"]),
                    source="market_anchor_members",
                ),
            )

    return AnchorDictionary(
        trade_date=trade_date,
        terms=sorted(terms.values(), key=lambda item: (-len(item.term), item.anchor_type, item.name)),
    )


def _connect_market(config: RadarConfig) -> sqlite3.Connection:
    config.market_database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.market_database_path)
    conn.row_factory = sqlite3.Row
    migrate_market_db(conn)
    return conn


def _add_term(terms: dict[tuple[str, str], AnchorTerm], term: AnchorTerm) -> None:
    if not _usable_term(term.term):
        return
    terms[(term.anchor_id, term.term)] = term


def _usable_term(value: str) -> bool:
    text = value.strip()
    if len(text) < 2:
        return False
    return any(char.isalnum() for char in text)


def _aliases(value: str) -> list[str]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]
