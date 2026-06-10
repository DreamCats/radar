from __future__ import annotations
import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Iterable
from radar.core.config import load_config
from radar.core.filtering import is_group_blacklisted
HIGH_VALUE_CATEGORIES = ("research", "event", "recommendation", "industry")
DEFAULT_SNIPPET_CHARS = 180
CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
TS_CODE_RE = re.compile(r"\b\d{6}\.(?:SH|SZ|BJ)\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+")
SPACE_RE = re.compile(r"\s+")
NOISY_STOCK_NAMES = {"机器人", "国联民生", "国泰海通"}
EVIDENCE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("调研/交流", ("调研", "董秘", "专家", "交流", "反馈", "纪要")),
    ("报告/更新", ("报告", "更新", "点评", "深度", "业绩", "测算")),
    ("路演/推票", ("路演", "反路演", "晨会", "1v1", "一对一")),
    ("推荐/call", ("推荐", "强推", "强call", "call", "关注", "首推")),
    ("行业逻辑", ("涨价", "缺货", "产能", "订单", "客户", "AI", "算力", "国产", "服务器")),
    ("行情确认", ("涨停", "放量", "成交额", "大涨", "异动", "冲高", "回落")),
    ("风险/反证", ("风险", "澄清", "下修", "不及预期", "亏损", "减持")),
)
@dataclass(frozen=True)
class Stock:
    ts_code: str; symbol: str; name: str
@dataclass
class MessageRow:
    message_id: str; source: str; sender: str; message_time: str; raw_content: str
    group_name: str | None; category: str | None; confidence: float | None
    @property
    def conversation(self) -> str:
        return self.group_name or self.sender
@dataclass
class CandidateStats:
    stock: Stock
    raw_messages: list[MessageRow] = field(default_factory=list)
    unique_fingerprints: set[str] = field(default_factory=set)
    senders: set[str] = field(default_factory=set)
    conversations: set[str] = field(default_factory=set)
    category_counts: Counter[str] = field(default_factory=Counter)
    @property
    def score(self) -> tuple[int, int, int, int]:
        high_value = sum(self.category_counts.get(category, 0) for category in HIGH_VALUE_CATEGORIES)
        return (len(self.unique_fingerprints), len(self.conversations), high_value, len(self.raw_messages))
@dataclass
class EvidenceItem:
    row: MessageRow; fingerprint: str; evidence_types: list[str]; duplicate_count: int; watch_hits: list[str]
def main() -> None:
    args = parse_args()
    config = load_config(args.config_dir)
    radar_db = (args.database or config.database_path).expanduser()
    market_db = (args.market_database or config.market_database_path).expanduser()
    as_of = parse_datetime_arg(args.as_of) if args.as_of else latest_message_time(radar_db)
    window_start = parse_datetime_arg(args.window_start) if args.window_start else previous_close(as_of)
    evidence_start = as_of - timedelta(days=args.evidence_days)
    blacklist = [] if args.ignore_group_blacklist else config.filters.group_blacklist_patterns
    categories = tuple(args.category or HIGH_VALUE_CATEGORIES)
    stocks = load_stocks(market_db)
    stock_by_name = {stock.name: stock for stock in stocks}
    selected_stocks = [resolve_stock_arg(stock_by_name, value) for value in args.stock]
    included_stocks = [resolve_stock_arg(stock_by_name, value) for value in args.include_stock]
    trigger_messages = load_messages(
        radar_db,
        start=window_start,
        end=as_of,
        categories=categories,
        include_uncategorized=args.include_uncategorized,
        blacklist_patterns=blacklist,
    )
    candidates = discover_candidates(trigger_messages, stocks)
    if selected_stocks:
        candidates = {code: candidates.get(code, CandidateStats(stock=stock)) for code, stock in ((s.ts_code, s) for s in selected_stocks)}
    forced_codes = {stock.ts_code for stock in included_stocks}
    for stock in included_stocks:
        candidates.setdefault(stock.ts_code, CandidateStats(stock=stock))
    ranked = rank_candidates(candidates.values(), forced_codes=forced_codes, limit=args.limit_candidates)
    report = render_report(
        radar_db=radar_db,
        market_db=market_db,
        ranked=ranked,
        stocks=stocks,
        as_of=as_of,
        window_start=window_start,
        evidence_start=evidence_start,
        categories=categories,
        blacklist_count=len(blacklist),
        trigger_count=len(trigger_messages),
        max_evidence=args.max_evidence,
        snippet_chars=args.snippet_chars,
        watch_terms=tuple(args.watch_term),
    )
    if args.llm:
        if not selected_stocks:
            raise SystemExit("--llm 必须配合 --stock 使用，避免把自动候选池整包发给 LLM")
        report += render_llm_judgement(config=config, report=report, provider_name=args.llm_provider, model=args.llm_model, max_tokens=args.llm_max_tokens, temperature=args.llm_temperature)
    if args.out == "-":
        print(report)
        return
    out = args.out or default_out_path(as_of)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"written={out}")
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读验证：从新增消息发现股票，并回查最近 40 天证据链。")
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--market-database", type=Path, default=None)
    parser.add_argument("--as-of", default=None, help="判断时间，例如 2026-06-09 15:00")
    parser.add_argument("--window-start", default=None, help="新增消息窗口起点；默认 as-of 前一日 15:00")
    parser.add_argument("--evidence-days", type=int, default=40)
    parser.add_argument("--limit-candidates", type=int, default=20)
    parser.add_argument("--max-evidence", type=int, default=60)
    parser.add_argument("--snippet-chars", type=int, default=DEFAULT_SNIPPET_CHARS)
    parser.add_argument("--category", action="append", default=None, help="新增窗口保留的消息分类，可重复")
    parser.add_argument("--include-uncategorized", action="store_true", help="新增窗口包含未分类消息")
    parser.add_argument("--ignore-group-blacklist", action="store_true")
    parser.add_argument("--stock", action="append", default=[], help="只输出指定股票，可用中文名或 ts_code")
    parser.add_argument("--include-stock", action="append", default=[], help="自动候选之外额外强制包含某只股票")
    parser.add_argument("--watch-term", action="append", default=[], help="证据里额外标记的观察词，例如 水产")
    parser.add_argument("--llm", action="store_true", help="调用 LLM 基于证据链判断阶段，默认关闭思考")
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-max-tokens", type=int, default=2048)
    parser.add_argument("--llm-temperature", type=float, default=0.2)
    parser.add_argument("--out", type=Path, default=None, help="输出 Markdown 路径；传 - 打印到 stdout")
    return parser.parse_args()
def parse_datetime_arg(value: str) -> datetime:
    normalized = value.strip().replace(" ", "T", 1)
    if len(normalized) == 10:
        return datetime.fromisoformat(normalized + "T23:59:59")
    return datetime.fromisoformat(normalized)
def previous_close(as_of: datetime) -> datetime:
    return datetime.combine(as_of.date() - timedelta(days=1), time(15, 0))
def default_out_path(as_of: datetime) -> Path:
    stamp = as_of.strftime("%Y%m%d-%H%M%S")
    return Path("tmp") / f"stock-evidence-chain-{stamp}.md"
def latest_message_time(database: Path) -> datetime:
    with readonly_conn(database) as conn:
        value = conn.execute("SELECT MAX(message_time) FROM messages").fetchone()[0]
    if not value:
        raise SystemExit(f"messages 为空: {database}")
    return datetime.fromisoformat(value)
def readonly_conn(database: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
def load_stocks(market_database: Path) -> list[Stock]:
    by_code: dict[str, Stock] = {}
    with readonly_conn(market_database) as conn:
        rows = conn.execute("SELECT data FROM tushare_cache WHERE api_name='stock_basic'").fetchall()
    for row in rows:
        for item in json.loads(row["data"]):
            ts_code = str(item.get("ts_code") or "")
            symbol = str(item.get("symbol") or "")
            name = str(item.get("name") or "")
            if not ts_code or not symbol or not usable_stock_name(name):
                continue
            by_code[ts_code] = Stock(ts_code=ts_code, symbol=symbol, name=name)
    if not by_code:
        raise SystemExit(f"market 库缺少 stock_basic 缓存: {market_database}")
    return sorted(by_code.values(), key=lambda stock: len(stock.name), reverse=True)
def usable_stock_name(name: str) -> bool:
    if len(name) < 2:
        return False
    return not name.startswith(("*ST", "ST"))
def resolve_stock_arg(stock_by_name: dict[str, Stock], value: str) -> Stock:
    normalized = value.strip().upper()
    for stock in stock_by_name.values():
        if normalized in {stock.ts_code.upper(), stock.symbol}:
            return stock
    stock = stock_by_name.get(value.strip())
    if stock is None:
        raise SystemExit(f"找不到股票: {value}")
    return stock
def load_messages(
    database: Path,
    *,
    start: datetime,
    end: datetime,
    categories: tuple[str, ...],
    include_uncategorized: bool,
    blacklist_patterns: list[str],
) -> list[MessageRow]:
    category_clause = ",".join(["?"] * len(categories))
    where = ["m.message_time >= ?", "m.message_time <= ?"]
    params: list[object] = [start.isoformat(), end.isoformat()]
    if categories:
        clause = f"c.category IN ({category_clause})"
        params.extend(categories)
        if include_uncategorized:
            clause = f"({clause} OR c.category IS NULL)"
        where.append(clause)
    sql = f"""
        SELECT m.message_id, m.source, m.sender, m.message_time, m.raw_content, m.group_name,
               c.category, c.confidence
        FROM messages m
        LEFT JOIN message_classifications c ON c.message_id = m.message_id
        WHERE {" AND ".join(where)}
        ORDER BY m.message_time ASC, m.message_id ASC
    """
    with readonly_conn(database) as conn:
        rows = conn.execute(sql, params).fetchall()
    messages = [row_to_message(row) for row in rows]
    return [msg for msg in messages if not is_group_blacklisted(msg.group_name, blacklist_patterns)]
def row_to_message(row: sqlite3.Row) -> MessageRow:
    return MessageRow(
        message_id=row["message_id"],
        source=row["source"],
        sender=row["sender"],
        message_time=row["message_time"],
        raw_content=row["raw_content"],
        group_name=row["group_name"],
        category=row["category"],
        confidence=row["confidence"],
    )
def discover_candidates(messages: list[MessageRow], stocks: list[Stock]) -> dict[str, CandidateStats]:
    candidates: dict[str, CandidateStats] = {}
    for message in messages:
        matched = detect_stocks(message.raw_content, stocks, strict=True)
        if not matched:
            continue
        fingerprint = content_fingerprint(message.raw_content)
        for stock in matched:
            stats = candidates.setdefault(stock.ts_code, CandidateStats(stock=stock))
            stats.raw_messages.append(message)
            stats.unique_fingerprints.add(fingerprint)
            stats.senders.add(message.sender)
            stats.conversations.add(message.conversation)
            stats.category_counts[message.category or "unclassified"] += 1
    return candidates
def rank_candidates(candidates: Iterable[CandidateStats], *, forced_codes: set[str], limit: int) -> list[CandidateStats]:
    forced: list[CandidateStats] = []
    regular: list[CandidateStats] = []
    for candidate in candidates:
        if candidate.stock.ts_code in forced_codes:
            forced.append(candidate)
        else:
            regular.append(candidate)
    ranked_regular = sorted(regular, key=lambda item: item.score, reverse=True)[:limit]
    regular_codes = {candidate.stock.ts_code for candidate in ranked_regular}
    ranked_forced = sorted([item for item in forced if item.stock.ts_code not in regular_codes], key=lambda item: item.score, reverse=True)
    return ranked_forced + ranked_regular
def detect_stocks(text: str, stocks: list[Stock], *, strict: bool = False) -> list[Stock]:
    matched: dict[str, Stock] = {}
    upper_text = text.upper()
    codes = set(CODE_RE.findall(text))
    ts_codes = set(TS_CODE_RE.findall(upper_text))
    for stock in stocks:
        by_code = stock.symbol in codes or stock.ts_code.upper() in ts_codes
        by_name = stock.name in text and (not strict or has_stock_context(text, stock))
        if by_name or by_code:
            matched[stock.ts_code] = stock
    return list(matched.values())
def has_stock_context(text: str, stock: Stock) -> bool:
    if len(stock.name) > 3 and stock.name not in NOISY_STOCK_NAMES:
        return True
    markers = (
        f"#{stock.name}",
        f"${stock.name}",
        f"【{stock.name}】",
        f"[{stock.name}]",
        f"「{stock.name}」",
        f"《{stock.name}》",
        f"{stock.name}：",
        f"{stock.name}:",
    )
    return any(marker in text for marker in markers)
def render_report(
    *, radar_db: Path, market_db: Path, ranked: list[CandidateStats], stocks: list[Stock], as_of: datetime,
    window_start: datetime, evidence_start: datetime, categories: tuple[str, ...], blacklist_count: int,
    trigger_count: int, max_evidence: int, snippet_chars: int, watch_terms: tuple[str, ...],
) -> str:
    lines = [
        "# 个股证据链 probe",
        "",
        "## 运行参数",
        "",
        f"- 判断时间：`{as_of.isoformat(timespec='seconds')}`",
        f"- 新增窗口：`{window_start.isoformat(timespec='seconds')}` -> `{as_of.isoformat(timespec='seconds')}`",
        f"- 证据窗口：`{evidence_start.isoformat(timespec='seconds')}` -> `{as_of.isoformat(timespec='seconds')}`",
        f"- 新增窗口分类：{', '.join(categories)}",
        f"- 群黑名单数量：{blacklist_count}",
        f"- 降噪后新增消息：{trigger_count} 条",
        f"- 候选股票：{len(ranked)} 只",
        "",
        "## 候选股票",
        "",
    ]
    if not ranked:
        lines.append("未发现候选股票。")
        return "\n".join(lines) + "\n"
    lines.extend(render_candidate_table(ranked))
    for candidate in ranked:
        lines.extend(render_stock_section(
            radar_db=radar_db, market_db=market_db, stock=candidate.stock, trigger_stats=candidate,
            stocks=stocks, evidence_start=evidence_start, as_of=as_of, max_evidence=max_evidence,
            snippet_chars=snippet_chars, watch_terms=watch_terms,
        ))
    return "\n".join(lines) + "\n"
def render_candidate_table(candidates: list[CandidateStats]) -> list[str]:
    lines = [
        "| 股票 | 代码 | 触发消息 | 去重后 | 发送人 | 会话 | 分类分布 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in candidates:
        lines.append(
            "| "
            f"{item.stock.name} | `{item.stock.ts_code}` | {len(item.raw_messages)} | "
            f"{len(item.unique_fingerprints)} | {len(item.senders)} | {len(item.conversations)} | "
            f"{format_counter(item.category_counts)} |"
        )
    lines.append("")
    return lines
def render_stock_section(
    *, radar_db: Path, market_db: Path, stock: Stock, trigger_stats: CandidateStats, stocks: list[Stock],
    evidence_start: datetime, as_of: datetime, max_evidence: int, snippet_chars: int, watch_terms: tuple[str, ...],
) -> list[str]:
    evidence = load_stock_evidence(radar_db, stock=stock, stocks=stocks, start=evidence_start, end=as_of, max_items=max_evidence, watch_terms=watch_terms)
    type_counts = Counter(kind for item in evidence for kind in item.evidence_types)
    watch_count = sum(1 for item in evidence if item.watch_hits)
    market_summary = summarize_market(market_db, stock.ts_code, evidence_start, as_of)
    lines = [
        "",
        f"## {stock.name} `{stock.ts_code}`",
        "",
        "### 触发摘要",
        "",
        f"- 新增窗口触发消息：{len(trigger_stats.raw_messages)} 条，去重后 {len(trigger_stats.unique_fingerprints)} 条",
        f"- 发送人 / 会话：{len(trigger_stats.senders)} / {len(trigger_stats.conversations)}",
        f"- 新增窗口分类：{format_counter(trigger_stats.category_counts)}",
        f"- 40 天证据：{len(evidence)} 条（最多展示 {max_evidence} 条）",
        f"- 证据类型：{format_counter(type_counts)}",
    ]
    if market_summary:
        lines.append(f"- 行情摘要：{market_summary}")
    if watch_terms:
        lines.append(f"- 观察词命中：{watch_count} 条，观察词：{', '.join(watch_terms)}")
    lines.extend(["", "### 证据时间线", ""])
    if not evidence:
        lines.append("未找到历史证据。")
        return lines
    lines.append("| 时间 | 分类 | 类型 | 来源 | 发送人 | 会话 | 去重 | 观察词 | 证据 |")
    lines.append("| --- | --- | --- | --- | --- | --- | ---: | --- | --- |")
    for item in evidence:
        row = item.row
        lines.append(
            "| "
            f"{row.message_time} | {row.category or 'unclassified'} | "
            f"{', '.join(item.evidence_types) or '未分层'} | {row.source} | "
            f"{escape_cell(row.sender)} | {escape_cell(row.conversation)} | "
            f"{item.duplicate_count} | {escape_cell(', '.join(item.watch_hits))} | "
            f"{escape_cell(snippet(row.raw_content, snippet_chars))} |"
        )
    return lines
def load_stock_evidence(
    database: Path, *, stock: Stock, stocks: list[Stock], start: datetime, end: datetime, max_items: int,
    watch_terms: tuple[str, ...],
) -> list[EvidenceItem]:
    rows = query_stock_messages(database, stock=stock, start=start, end=end)
    confirmed = [row for row in rows if stock in detect_stocks(row.raw_content, stocks)]
    duplicate_counts = Counter(content_fingerprint(row.raw_content) for row in confirmed)
    deduped: list[EvidenceItem] = []
    seen: set[str] = set()
    for row in confirmed:
        fingerprint = content_fingerprint(row.raw_content)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(EvidenceItem(
            row=row, fingerprint=fingerprint, evidence_types=classify_evidence(row),
            duplicate_count=duplicate_counts[fingerprint], watch_hits=watch_hits(row.raw_content, watch_terms),
        ))
    return deduped[:max_items]
def query_stock_messages(database: Path, *, stock: Stock, start: datetime, end: datetime) -> list[MessageRow]:
    like_name = f"%{stock.name}%"
    like_symbol = f"%{stock.symbol}%"
    like_ts_code = f"%{stock.ts_code}%"
    sql = """
        SELECT m.message_id, m.source, m.sender, m.message_time, m.raw_content, m.group_name,
               c.category, c.confidence
        FROM messages m
        LEFT JOIN message_classifications c ON c.message_id = m.message_id
        WHERE m.message_time >= ?
          AND m.message_time <= ?
          AND (m.raw_content LIKE ? OR m.raw_content LIKE ? OR UPPER(m.raw_content) LIKE ?)
        ORDER BY m.message_time ASC, m.message_id ASC
    """
    with readonly_conn(database) as conn:
        rows = conn.execute(
            sql,
            [start.isoformat(), end.isoformat(), like_name, like_symbol, like_ts_code.upper()],
        ).fetchall()
    return [row_to_message(row) for row in rows]
def classify_evidence(row: MessageRow) -> list[str]:
    text = row.raw_content
    kinds = [label for label, keywords in EVIDENCE_KEYWORDS if any(keyword in text for keyword in keywords)]
    if row.category == "event" and "事件" not in kinds:
        kinds.append("事件")
    if row.category == "recommendation" and "推荐/call" not in kinds:
        kinds.append("推荐/call")
    if row.category == "chat":
        kinds.append("群聊扩散")
    return kinds
def watch_hits(text: str, terms: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        if term not in text:
            continue
        contexts = []
        for match in re.finditer(re.escape(term), text):
            start = max(match.start() - 2, 0)
            end = min(match.end() + 2, len(text))
            contexts.append(text[start:end])
        hits.append(f"{term}({';'.join(sorted(set(contexts))[:3])})")
    return hits
def summarize_market(market_database: Path, ts_code: str, start: datetime, end: datetime) -> str:
    start_key = start.strftime("%Y%m%d")
    end_key = end.strftime("%Y%m%d")
    sql = """
        SELECT date_key, data
        FROM tushare_history
        WHERE api_name='daily' AND ts_code=? AND date_key>=? AND date_key<=?
        ORDER BY date_key ASC
    """
    with readonly_conn(market_database) as conn:
        rows = conn.execute(sql, [ts_code, start_key, end_key]).fetchall()
    if len(rows) < 2:
        return ""
    parsed = [(row["date_key"], json.loads(row["data"])) for row in rows]
    first_date, first = parsed[0]
    last_date, last = parsed[-1]
    first_close = to_float(first.get("close"))
    last_close = to_float(last.get("close"))
    amount = to_float(last.get("amount"))
    if first_close is None or last_close is None or first_close == 0:
        return ""
    pct = (last_close / first_close - 1) * 100
    amount_text = f"，末日成交额 {amount / 100000:.1f} 亿" if amount is not None else ""
    return f"{first_date} 收 {first_close:.2f} -> {last_date} 收 {last_close:.2f}，区间 {pct:+.1f}%{amount_text}"
def to_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
def content_fingerprint(text: str) -> str:
    normalized = URL_RE.sub("", text)
    normalized = SPACE_RE.sub("", normalized)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()
def snippet(text: str, limit: int) -> str:
    normalized = SPACE_RE.sub(" ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "..."
def format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "-"
    return " / ".join(f"{key} {value}" for key, value in counter.most_common())
def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")
def render_llm_judgement(*, config, report: str, provider_name: str | None, model: str | None, max_tokens: int, temperature: float) -> str:
    from radar.core.llm import chat
    system = "你是个人投资者的投研证据链助手。只基于用户给出的证据判断，不编造外部信息。输出中文 Markdown，必须引用证据里的时间点、发送人或来源。不要给买卖建议。"
    user = f"""
请基于下面的个股证据链，判断这只股票当前处于哪个阶段，并解释为什么。

阶段只能选一个：
- lead（线索期）
- seed（种子期）
- formed（论证期）
- spreading（扩散期）
- pricing（定价期）
- crowded（拥挤期）

请按这个结构输出：
1. 当前阶段
2. 阶段理由
3. 关键证据链
4. 相比早期是否有增量
5. 定价/拥挤风险
6. 还需要继续验证什么

注意：“降噪后新增消息”是全市场/全窗口消息数，不是该股票自己的消息数；判断个股热度只能使用“新增窗口触发消息”、去重后数量、发送人、会话和证据时间线。

证据如下：
{report[:30000]}
""".strip()
    content = chat(config, [{"role": "system", "content": system}, {"role": "user", "content": user}], provider_name=provider_name, model=model, temperature=temperature, max_tokens=max_tokens, disable_thinking=True)
    return "\n\n## LLM 阶段判断\n\n" + content.strip() + "\n"
if __name__ == "__main__":
    main()
