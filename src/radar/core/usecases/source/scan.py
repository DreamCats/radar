from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta

from radar.core.config import RadarConfig
from radar.core.models import RawMessage
from radar.core.store import connect, init_db
from radar.core.usecases.source.models import SourceSignalCandidate, SourceSignalResult, SourceStructure
from radar.core.usecases.source.storage import list_source_structures

MIN_SOURCE_CONFIDENCE = 0.65
OLD_THEME_COMBO_THRESHOLD = 8
SOURCE_SEED_MIN_TRADABILITY = 0.32
TRADABLE_TERMS = (
    "AI", "GPU", "CPU", "ASIC", "HBM", "PCB", "CCL", "PTFE", "MLCC", "算力", "服务器", "数据中心",
    "半导体", "芯片", "封装", "玻璃基板", "光模块", "光通信", "电源", "储能", "电池", "机器人",
    "具身智能", "稀土", "煤", "铜", "铝", "钢", "化工", "航运", "集运", "运价", "军工", "卫星",
    "低空", "汽车", "医药", "创新药", "供给", "产能", "涨价", "订单", "限制", "关税", "出海",
    "国产替代", "台积电", "英伟达", "SpaceX", "特斯拉",
)
WEAK_SEED_TERMS = ("人民币", "金融强国", "非农", "劳动者", "就业", "语典", "货币")


def scan_source_signals(
    config: RadarConfig,
    *,
    start_time: datetime,
    end_time: datetime,
    as_of_time: datetime | None = None,
    lookback_days: int = 60,
    limit: int = 20,
    save_snapshot: bool = True,
) -> SourceSignalResult:
    if end_time <= start_time:
        raise ValueError("end_time 必须晚于 start_time")
    if lookback_days < 7 or lookback_days > 180:
        raise ValueError("lookback_days 必须在 7 到 180 之间")
    if limit < 1 or limit > 100:
        raise ValueError("limit 必须在 1 到 100 之间")
    as_of = as_of_time or end_time
    conn = connect(config.database_path)
    try:
        init_db(conn)
        corpus_start = start_time - timedelta(days=lookback_days)
        structures = list_source_structures(conn, start_time=start_time, end_time=min(end_time, as_of), min_confidence=MIN_SOURCE_CONFIDENCE)
        candidates = _build_candidates(conn, structures, corpus_start, as_of)
        visible = [item for item in candidates if item.status != "old_theme"]
        visible.sort(key=_sort_key)
        result = SourceSignalResult(
            start_time=start_time,
            end_time=end_time,
            as_of_time=as_of,
            lookback_days=lookback_days,
            scanned_count=len(structures),
            candidate_count=len(candidates),
            candidates=visible[:limit],
        )
        if save_snapshot:
            _store_signal_snapshots(conn, result)
        return result
    finally:
        conn.close()


def _build_candidates(
    conn: sqlite3.Connection,
    structures: list[SourceStructure],
    corpus_start: datetime,
    as_of: datetime,
) -> list[SourceSignalCandidate]:
    candidates_by_signal: dict[str, SourceSignalCandidate] = {}
    first_messages = _load_messages_by_id(conn, [item.message_id for item in structures])
    for structure in _dedupe_structures(structures):
        first = first_messages.get(structure.message_id)
        if first is None:
            continue
        tradability = _tradability_score(structure, first.raw_content)
        if tradability <= 0:
            continue
        prior_anchor = _count_term(conn, structure.anchor_span, start_time=corpus_start, end_time=first.message_time, end_exclusive=True)
        if prior_anchor == 0:
            continue
        prior_modifier = _count_term(conn, structure.modifier_span, start_time=corpus_start, end_time=first.message_time, end_exclusive=True)
        prior_messages = _messages_for_combo(conn, structure, start_time=corpus_start, end_time=first.message_time, end_exclusive=True)
        prior_exact = sum(1 for message in prior_messages if _contains_text(message.raw_content, structure.novel_span))
        prior_combo = len(prior_messages)
        mentions = _messages_for_combo(conn, structure, start_time=first.message_time, end_time=as_of, end_exclusive=False)
        followups = [message for message in mentions if message.message_id != first.message_id]
        mapped_stocks = _mapped_stocks(conn, [message.message_id for message in mentions])
        status = _status(prior_combo, followups, mapped_stocks)
        if status == "source_seed" and tradability < SOURCE_SEED_MIN_TRADABILITY:
            continue
        score, novelty, earliness, askability, trade = _score(
            prior_exact,
            prior_combo,
            prior_anchor,
            len(mentions),
            _group_count(mentions),
            _sender_count(followups),
            _group_count(followups),
            mapped_stocks,
            _source_quality(first, structure),
            tradability,
        )
        candidate = SourceSignalCandidate(
            signal_id=_signal_id(structure),
            status=status,  # type: ignore[arg-type]
            anchor_span=structure.anchor_span,
            modifier_span=structure.modifier_span,
            novel_span=structure.novel_span,
            relation_type=structure.relation_type,
            score=score,
            novelty_strength=novelty,
            earliness_score=earliness,
            askability_score=askability,
            trade_score=trade,
            first_message_id=first.message_id,
            first_seen_time=first.message_time,
            first_sender=first.sender,
            first_group_name=first.group_name,
            first_snippet=_snippet(first.raw_content),
            prior_anchor_mentions=prior_anchor,
            prior_modifier_mentions=prior_modifier,
            prior_exact_mentions=prior_exact,
            prior_combo_mentions=prior_combo,
            asof_mentions=len(mentions),
            asof_groups=_group_count(mentions),
            asof_senders=_sender_count(mentions),
            followup_groups=_group_count(followups),
            followup_senders=_sender_count(followups),
            mapped_stocks=mapped_stocks,
            ask_question=structure.ask_question,
            evidence=_evidence(structure, prior_anchor, prior_modifier, prior_exact, prior_combo, mentions, followups, mapped_stocks),
        )
        current = candidates_by_signal.get(candidate.signal_id)
        if current is None or candidate.first_seen_time < current.first_seen_time:
            candidates_by_signal[candidate.signal_id] = candidate
    return list(candidates_by_signal.values())


def _dedupe_structures(structures: list[SourceStructure]) -> list[SourceStructure]:
    best: dict[str, SourceStructure] = {}
    for structure in structures:
        key = _signal_id(structure)
        current = best.get(key)
        if current is None or structure.message_time < current.message_time or (
            structure.message_time == current.message_time and structure.confidence > current.confidence
        ):
            best[key] = structure
    return sorted(best.values(), key=lambda item: (item.message_time, item.structure_id))


def _load_messages_by_id(conn: sqlite3.Connection, message_ids: list[str]) -> dict[str, RawMessage]:
    if not message_ids:
        return {}
    placeholders = ",".join("?" for _ in message_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM messages
        WHERE message_id IN ({placeholders})
        """,
        message_ids,
    ).fetchall()
    return {message.message_id: message for message in [_message_from_row(row) for row in rows]}


def _messages_for_combo(
    conn: sqlite3.Connection,
    structure: SourceStructure,
    *,
    start_time: datetime,
    end_time: datetime,
    end_exclusive: bool,
) -> list[RawMessage]:
    search_terms = _search_terms(structure)
    for search_term in search_terms:
        rows = _query_messages_by_fts(conn, search_term, start_time=start_time, end_time=end_time, end_exclusive=end_exclusive)
        messages = [message for message in [_message_from_row(row) for row in rows] if _contains_combo_text(message.raw_content, structure)]
        if messages:
            return messages
    if search_terms:
        return []
    operator = "<" if end_exclusive else "<="
    rows = conn.execute(
        f"""
        SELECT *
        FROM messages
        WHERE message_time >= ?
          AND message_time {operator} ?
          AND (
            raw_content LIKE ?
            OR (raw_content LIKE ? AND raw_content LIKE ?)
          )
        ORDER BY message_time ASC, message_id ASC
        """,
        (
            start_time.isoformat(),
            end_time.isoformat(),
            _like(structure.novel_span),
            _like(structure.anchor_span),
            _like(structure.modifier_span),
        ),
    ).fetchall()
    return [_message_from_row(row) for row in rows]


def _count_term(conn: sqlite3.Connection, term: str, *, start_time: datetime, end_time: datetime, end_exclusive: bool) -> int:
    if not _compact(term):
        return 0
    if not _can_use_fts(term):
        return 1
    if _can_use_fts(term):
        rows = _query_messages_by_fts(conn, term, start_time=start_time, end_time=end_time, end_exclusive=end_exclusive)
        return sum(1 for row in rows if _contains_text(str(row["raw_content"]), term))
    return 0


def _query_messages_by_fts(
    conn: sqlite3.Connection,
    term: str,
    *,
    start_time: datetime,
    end_time: datetime,
    end_exclusive: bool,
) -> list[sqlite3.Row]:
    operator = "<" if end_exclusive else "<="
    try:
        return conn.execute(
            f"""
            SELECT m.*
            FROM messages_fts fts
            JOIN messages m ON m.message_id = fts.message_id
            WHERE messages_fts MATCH ?
              AND m.message_time >= ?
              AND m.message_time {operator} ?
            ORDER BY m.message_time ASC, m.message_id ASC
            """,
            (_fts_query(term), start_time.isoformat(), end_time.isoformat()),
        ).fetchall()
    except sqlite3.Error:
        return []


def _contains_combo_text(text: str, structure: SourceStructure) -> bool:
    return _contains_text(text, structure.novel_span) or (
        _contains_text(text, structure.anchor_span) and _contains_text(text, structure.modifier_span)
    )


def _message_from_row(row: sqlite3.Row) -> RawMessage:
    return RawMessage(
        message_id=str(row["message_id"]),
        source=str(row["source"]),  # type: ignore[arg-type]
        sender=str(row["sender"]),
        message_time=datetime.fromisoformat(str(row["message_time"])),
        raw_content=str(row["raw_content"]),
        group_name=str(row["group_name"]) if row["group_name"] else None,
        fetch_time=datetime.fromisoformat(str(row["fetch_time"])),
        fetch_window=str(row["fetch_window"]),
    )


def _contains_text(text: str, value: str) -> bool:
    if not value:
        return False
    compact = _compact(value)
    text_compact = _compact(text)
    return compact in text_compact or compact.upper() in text_compact.upper()


def _like(value: str) -> str:
    return f"%{_compact(value)}%"


def _search_terms(structure: SourceStructure) -> list[str]:
    terms = [structure.novel_span, structure.modifier_span, structure.anchor_span]
    usable = [term for term in terms if _can_use_fts(term)]
    return sorted(dict.fromkeys(usable), key=lambda value: len(_compact(value)), reverse=True)


def _can_use_fts(value: str) -> bool:
    return len(_compact(value)) >= 3


def _fts_query(value: str) -> str:
    escaped = _compact(value).replace('"', '""')
    return f'"{escaped}"'


def _mapped_stocks(conn: sqlite3.Connection, message_ids: list[str]) -> list[str]:
    if not message_ids:
        return []
    placeholders = ",".join("?" for _ in message_ids)
    rows = conn.execute(
        f"""
        SELECT stock_name, COUNT(*) AS c
        FROM recommendation_events
        WHERE message_id IN ({placeholders})
        GROUP BY stock_name
        ORDER BY c DESC, stock_name
        LIMIT 12
        """,
        message_ids,
    ).fetchall()
    return [str(row["stock_name"]) for row in rows]


def _status(prior_combo: int, followups: list[RawMessage], mapped_stocks: list[str]) -> str:
    if prior_combo > OLD_THEME_COMBO_THRESHOLD:
        return "old_theme"
    if mapped_stocks:
        return "mapped"
    if _group_count(followups) >= 3 or _sender_count(followups) >= 2:
        return "spreading_watch"
    return "source_seed"


def _score(
    prior_exact: int,
    prior_combo: int,
    prior_anchor: int,
    asof_mentions: int,
    asof_groups: int,
    followup_senders: int,
    followup_groups: int,
    mapped_stocks: list[str],
    source_quality: float,
    tradability: float,
) -> tuple[float, float, float, float, float]:
    novelty = max(0.0, 1.0 - min(prior_exact, 10) * 0.05 - min(prior_combo, 10) * 0.08 - (0.15 if prior_anchor == 0 else 0))
    earliness = 0.35 if asof_groups >= 5 else 0.55 if asof_groups >= 3 else 0.75 if asof_mentions >= 3 else 1.0
    askability = round(novelty * 0.4 + earliness * 0.3 + source_quality * 0.15 + tradability * 0.15, 2)
    trade = min(1.0, followup_senders * 0.18 + followup_groups * 0.12 + tradability * 0.2)
    if mapped_stocks:
        trade = max(trade, 0.8)
    total = round(askability * 60 + trade * 25 + min(asof_groups, 5) * 3, 1)
    return total, round(novelty, 2), round(earliness, 2), askability, round(trade, 2)


def _source_quality(message: RawMessage, structure: SourceStructure) -> float:
    score = 0.55
    if structure.relation_type == "A化B":
        score += 0.12
    if structure.ask_question:
        score += 0.08
    if len(message.raw_content) <= 500:
        score += 0.1
    return min(score, 1.0)


def _tradability_score(structure: SourceStructure, content: str) -> float:
    text = _compact(" ".join([structure.anchor_span, structure.modifier_span, structure.novel_span, content]))
    upper = text.upper()
    hits = sum(1 for term in TRADABLE_TERMS if _compact(term).upper() in upper)
    score = min(0.8, hits * 0.16)
    if structure.relation_type in {"A化B", "prefix-anchor"}:
        score += 0.12
    if any(term in text for term in ("推荐", "关注", "产业链", "供应商", "涨价", "订单", "产能", "替代")):
        score += 0.12
    if any(term in text for term in WEAK_SEED_TERMS):
        score -= 0.25
    return max(0.0, min(1.0, score))


def _sort_key(item: SourceSignalCandidate) -> tuple[int, float, float, float, datetime]:
    status_rank = {"spreading_watch": 0, "mapped": 1, "source_seed": 2, "old_theme": 9}[item.status]
    relation_rank = {"A化B": 0, "prefix-anchor": 1, "modifier-anchor": 2, "anchor-extension": 3, "other": 9}[item.relation_type]
    return (status_rank, -item.score, relation_rank, -item.novelty_strength, item.first_seen_time)


def _store_signal_snapshots(conn: sqlite3.Connection, result: SourceSignalResult) -> None:
    now = datetime.now()
    for item in result.candidates:
        conn.execute(
            """
            INSERT INTO source_signal_snapshots (
                snapshot_id, signal_id, status, anchor_span, modifier_span, novel_span,
                relation_type, score, novelty_strength, earliness_score, askability_score,
                trade_score, first_message_id, first_seen_time, as_of_time, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                item.signal_id,
                item.status,
                item.anchor_span,
                item.modifier_span,
                item.novel_span,
                item.relation_type,
                item.score,
                item.novelty_strength,
                item.earliness_score,
                item.askability_score,
                item.trade_score,
                item.first_message_id,
                item.first_seen_time.isoformat(),
                result.as_of_time.isoformat(),
                json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
                now.isoformat(),
            ),
        )
    conn.commit()


def _evidence(
    structure: SourceStructure,
    prior_anchor: int,
    prior_modifier: int,
    prior_exact: int,
    prior_combo: int,
    mentions: list[RawMessage],
    followups: list[RawMessage],
    mapped_stocks: list[str],
) -> list[str]:
    out = [
        f"锚点 {structure.anchor_span} 历史 {prior_anchor} 次",
        f"修饰 {structure.modifier_span} 历史 {prior_modifier} 次",
        f"精确组合历史 {prior_exact} 次",
        f"锚点+修饰组合历史 {prior_combo} 次",
        f"截至 as_of {len(mentions)} 次/{_group_count(mentions)} 群/{_sender_count(mentions)} 人",
    ]
    if followups:
        out.append(f"首现后接力 {_sender_count(followups)} 人/{_group_count(followups)} 群")
    if mapped_stocks:
        out.append("已映射个股：" + "、".join(mapped_stocks[:6]))
    return out


def _signal_id(structure: SourceStructure) -> str:
    raw = f"{structure.anchor_span}::{structure.relation_type}::{structure.modifier_span}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _group_count(messages: list[RawMessage]) -> int:
    return len({message.group_name for message in messages if message.group_name})


def _sender_count(messages: list[RawMessage]) -> int:
    return len({message.sender for message in messages if message.sender})


def _compact(value: str) -> str:
    return "".join(str(value or "").strip().split())


def _snippet(value: str, limit: int = 120) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit] + "..."
