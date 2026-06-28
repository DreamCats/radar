from __future__ import annotations

import re
from html import escape

from radar.core.usecases.catalyst_strategy.models import (
    CatalystStockAnalysis,
    CatalystStockContext,
    CatalystStrategyEvidence,
    CatalystStrategyReport,
)


def render_report_html(report: CatalystStrategyReport) -> str:
    cards = "\n".join(_stock_card(report, analysis) for analysis in report.analyses)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Radar 催化词策略报告</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #08090b;
      --panel: #12141a;
      --panel-2: #191c24;
      --text: #edf0f7;
      --muted: #9aa3b2;
      --line: #2a2f3a;
      --accent: #5eead4;
      --warn: #fbbf24;
      --info: #38bdf8;
      --stock: #67e8f9;
      --term: #facc15;
      --number: #fbbf24;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    main {{ max-width: 980px; margin: 0 auto; padding: 28px 16px 44px; }}
    header {{ margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 20px; }}
    h3 {{ margin: 0 0 8px; font-size: 16px; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .grid {{ display: grid; gap: 14px; }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }}
    .stock-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }}
    .stock-code {{ color: var(--muted); font-size: 13px; }}
    .stock-source {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
    .chips {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0; }}
    .chip {{ border: 1px solid var(--line); background: var(--panel-2); border-radius: 999px; padding: 3px 8px; font-size: 12px; color: var(--muted); }}
    .summary {{ margin: 10px 0 0; padding-left: 18px; }}
    .valuation {{ border-left: 3px solid var(--accent); padding-left: 12px; margin-top: 12px; }}
    .scenario {{ border-left-color: var(--info); }}
    .skipped {{ border-left-color: var(--warn); }}
    .number-highlight {{ color: var(--number); font-weight: 750; text-decoration: underline; text-decoration-thickness: 1.5px; text-underline-offset: 3px; }}
    .stock-highlight {{ color: var(--stock); font-weight: 750; }}
    .term-highlight {{ color: var(--term); font-weight: 750; }}
    .snapshot {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; margin-top: 12px; }}
    .metric {{ background: var(--panel-2); border-radius: 6px; padding: 8px; }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ font-size: 14px; }}
    .snapshot-note {{ color: var(--warn); font-size: 12px; margin-top: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 6px 4px; text-align: left; }}
    th {{ color: var(--muted); font-weight: 500; }}
    details {{ margin-top: 12px; }}
    .evidence {{ margin-top: 10px; }}
    .evidence-meta {{ color: var(--muted); font-size: 12px; margin: 0 0 4px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; color: var(--muted); background: var(--panel-2); padding: 10px; border-radius: 6px; }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>Radar 催化词策略报告</h1>
    <div class="meta">生成时间：{escape(report.generated_at.isoformat(sep=" ", timespec="seconds"))}</div>
    <div class="meta">窗口：{escape(report.start_time.isoformat(sep=" ", timespec="minutes"))} ~ {escape(report.end_time.isoformat(sep=" ", timespec="minutes"))}</div>
    <div class="meta">催化词条目：{report.total_feed_items}，去重标的：{report.total_stocks}</div>
  </header>
  <section class="grid">
    {cards or '<article class="card">暂无符合条件的催化词标的。</article>'}
  </section>
</main>
</body>
</html>
"""


def _stock_card(report: CatalystStrategyReport, analysis: CatalystStockAnalysis) -> str:
    context = next(item for item in report.stocks if item.stock_key == analysis.stock_key)
    snapshot = context.market_snapshot
    valuation_class = f"valuation {_valuation_state_class(analysis)}"
    first_evidence = _first_evidence(context)
    return f"""<article class="card">
  <div class="stock-head">
    <div>
      <h2>{escape(analysis.stock_name)}</h2>
      <div class="stock-code">{escape(analysis.ts_code or analysis.stock_key)}</div>
      <div class="stock-source">{escape(_stock_source_line(context, first_evidence))}</div>
    </div>
    <div class="meta">证据 {len(context.evidence)} 条</div>
  </div>
  <div class="chips">{_chips(context.evidence[0].matched_terms if context.evidence else [])}</div>
  <ol class="summary">{''.join(f'<li>{escape(item)}</li>' for item in analysis.summary)}</ol>
  {_snapshot_html(snapshot)}
  <div class="{valuation_class}">
    <h3>{escape(_valuation_title(analysis))}</h3>
    <p>{_highlight_numbers(analysis.valuation_text or '原文缺少可测算数据。')}</p>
    {_valuation_metrics(analysis)}
  </div>
  {_risks_html(analysis)}
  <details>
    <summary>原文证据</summary>
    {''.join(_evidence_html(item, context) for item in context.evidence[:8])}
  </details>
</article>"""


def _chips(values: list[str]) -> str:
    return "".join(f'<span class="chip">{escape(value)}</span>' for value in values)


def _snapshot_html(snapshot) -> str:
    if snapshot is None:
        return ""
    metrics = [
        ("当前价", _money(snapshot.realtime_price, "元") or "-"),
        ("估算市值", _money(snapshot.estimated_total_mv_yi, "亿") or "-"),
        ("收盘市值", _money(snapshot.total_mv_yi, "亿") or "-"),
        ("PE TTM", _pe_ttm_text(snapshot)),
        ("PE分位", _pe_percentiles(snapshot)),
        ("TTM隐含利润", _implied_profit_text(snapshot)),
        ("最新营收", _period_money(snapshot.latest_financial_period, snapshot.latest_revenue_yi) or "-"),
        ("最新归母净利", _period_money(snapshot.latest_financial_period, snapshot.latest_net_profit_yi) or "-"),
        ("口径", snapshot.valuation_basis),
        ("交易日", snapshot.last_trade_date or "-"),
    ]
    snapshot_html = '<div class="snapshot">' + "".join(
        f'<div class="metric"><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>'
        for label, value in metrics
    ) + "</div>"
    return snapshot_html + _snapshot_notes_html(snapshot) + _financial_trend_html(snapshot)


def _valuation_metrics(analysis: CatalystStockAnalysis) -> str:
    if analysis.valuation_status != "provided":
        return ""
    metrics = [
        ("目标市值", _money(analysis.target_market_cap_yi, "亿")),
        ("目标价", _money(analysis.target_price, "元")),
        ("上涨空间", _pct(analysis.upside_pct)),
        ("置信度", analysis.confidence),
    ]
    return '<div class="snapshot">' + "".join(
        f'<div class="metric"><span>{escape(label)}</span><strong>{escape(value or "-")}</strong></div>'
        for label, value in metrics
    ) + "</div>"


def _risks_html(analysis: CatalystStockAnalysis) -> str:
    if not analysis.risks:
        return ""
    return "<h3>风险</h3><ul>" + "".join(f"<li>{escape(item)}</li>" for item in analysis.risks) + "</ul>"


def _valuation_state_class(analysis: CatalystStockAnalysis) -> str:
    if analysis.valuation_status == "provided":
        return ""
    if analysis.valuation_status == "scenario":
        return "scenario"
    return "skipped"


def _valuation_title(analysis: CatalystStockAnalysis) -> str:
    if analysis.valuation_status == "provided":
        return "估值推演"
    if analysis.valuation_status == "scenario":
        return "情景推演"
    if analysis.valuation_status == "error":
        return "分析失败"
    return "估值跳过"


def _financial_trend_html(snapshot) -> str:
    if not snapshot.financial_trend:
        return ""
    rows = "".join(
        "<tr>"
        f"<td>{escape(item.period)}</td>"
        f"<td>{escape(_money(item.revenue_yi, '亿') or '-')}</td>"
        f"<td>{escape(_money(item.net_profit_yi, '亿') or '-')}</td>"
        "</tr>"
        for item in snapshot.financial_trend
    )
    return (
        "<table><thead><tr><th>财报期</th><th>营收</th><th>归母净利</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _first_evidence(context: CatalystStockContext) -> CatalystStrategyEvidence | None:
    return min(context.evidence, key=lambda item: item.message_time, default=None)


def _stock_source_line(
    context: CatalystStockContext,
    evidence: CatalystStrategyEvidence | None,
) -> str:
    if evidence is None:
        return f"首提：{_time_text(context.first_message_time)}"
    return f"首提：{_time_text(evidence.message_time)} · {_speaker_text(evidence)}"


def _evidence_html(evidence: CatalystStrategyEvidence, context: CatalystStockContext) -> str:
    duplicate_text = f" · 合并 {evidence.duplicate_count} 条" if evidence.duplicate_count > 1 else ""
    return f"""<div class="evidence">
  <div class="evidence-meta">{escape(_time_text(evidence.message_time))} · {escape(_speaker_text(evidence))}{escape(duplicate_text)}</div>
  <pre>{_highlight_evidence(evidence, context)}</pre>
</div>"""


def _speaker_text(evidence: CatalystStrategyEvidence) -> str:
    parts = [str(evidence.source)]
    if evidence.sender:
        parts.append(evidence.sender)
    if evidence.group_name:
        parts.append(evidence.group_name)
    return " / ".join(parts)


def _time_text(value) -> str:
    return value.strftime("%m-%d %H:%M")


def _money(value: float | None, unit: str) -> str | None:
    return None if value is None else f"{value:.2f} {unit}"


def _period_money(period: str | None, value: float | None) -> str | None:
    amount = _money(value, "亿")
    if amount is None:
        return None
    return f"{period or '最新'} {amount}"


def _pe_ttm_text(snapshot) -> str:
    value = snapshot.estimated_pe_ttm or snapshot.pe_ttm
    if value is not None:
        return _multiple(value)
    if snapshot.latest_net_profit_yi is not None and snapshot.latest_net_profit_yi <= 0:
        return "亏损/不可用"
    if snapshot.error:
        return "缺行情"
    return "-"


def _implied_profit_text(snapshot) -> str:
    value = _money(snapshot.implied_net_profit_ttm_yi, "亿")
    if value is not None:
        return value
    if snapshot.latest_net_profit_yi is not None and snapshot.latest_net_profit_yi <= 0:
        return "PE不可用"
    return "-"


def _snapshot_notes_html(snapshot) -> str:
    notes = []
    if snapshot.error:
        notes.append(f"行情数据：{snapshot.error}")
    if snapshot.financial_error:
        notes.append(f"财务数据：{snapshot.financial_error}")
    if not notes:
        return ""
    return "".join(f'<div class="snapshot-note">{escape(note)}</div>' for note in notes)


def _pe_percentiles(snapshot) -> str:
    values = [
        _pct(snapshot.pe_ttm_percentile_60d),
        _pct(snapshot.pe_ttm_percentile_120d),
        _pct(snapshot.pe_ttm_percentile_250d),
    ]
    if all(value is None for value in values):
        return "-"
    return " / ".join(value or "-" for value in values) + "（60/120/250日）"


def _multiple(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}x"


def _pct(value: float | None) -> str | None:
    return None if value is None else f"{value:.1f}%"


_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?\s*"
    r"(?:万亿|亿元|亿|万元|元|倍|%|pct|XPE|xPE|PE|GW|MW|GWh|MWh|年|月|日|个月|只|颗|台|套|条|吨|e)?"
    r"(?![A-Za-z0-9])"
)


def _highlight_numbers(text: str) -> str:
    parts: list[str] = []
    last = 0
    for match in _NUMBER_RE.finditer(text):
        parts.append(escape(text[last : match.start()]))
        parts.append(f'<span class="number-highlight">{escape(match.group(0))}</span>')
        last = match.end()
    parts.append(escape(text[last:]))
    return "".join(parts)


def _highlight_evidence(evidence: CatalystStrategyEvidence, context: CatalystStockContext) -> str:
    tokens: list[tuple[str, str]] = []
    for value in (context.stock_name, context.ts_code, (context.ts_code or "").split(".")[0]):
        _append_highlight_token(tokens, value, "stock-highlight")
    for value in evidence.matched_terms:
        _append_highlight_token(tokens, value, "term-highlight")
    return _highlight_tokens(evidence.content, tokens)


def _append_highlight_token(
    tokens: list[tuple[str, str]],
    value: str | None,
    css_class: str,
) -> None:
    text = (value or "").strip()
    if len(text) < 2:
        return
    key = (text.lower(), css_class)
    if key in {(token.lower(), klass) for token, klass in tokens}:
        return
    tokens.append((text, css_class))


def _highlight_tokens(text: str, tokens: list[tuple[str, str]]) -> str:
    if not tokens:
        return escape(text)
    sorted_tokens = sorted(tokens, key=lambda item: len(item[0]), reverse=True)
    output: list[str] = []
    index = 0
    lower_text = text.lower()
    while index < len(text):
        match_token: tuple[str, str] | None = None
        for token, css_class in sorted_tokens:
            if lower_text.startswith(token.lower(), index):
                match_token = (token, css_class)
                break
        if match_token is None:
            output.append(escape(text[index]))
            index += 1
            continue
        token, css_class = match_token
        raw = text[index : index + len(token)]
        output.append(f'<span class="{css_class}">{escape(raw)}</span>')
        index += len(token)
    return "".join(output)
