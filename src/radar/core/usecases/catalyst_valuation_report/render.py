from __future__ import annotations

from html import escape

from radar.core.usecases.catalyst_valuation_report.models import (
    CatalystValuationEvidence,
    CatalystValuationReport,
    CatalystValuationStockContext,
)
from radar.core.usecases.catalyst_valuation_report.rules import extract_display_numbers


def render_report_html(report: CatalystValuationReport) -> str:
    cards = "\n".join(_stock_card(context) for context in report.stocks)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Radar 催化估值线索报告</title>
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
    h2 {{ margin: 0; font-size: 20px; }}
    h3 {{ margin: 14px 0 8px; font-size: 15px; }}
    button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-2);
      color: var(--text);
      padding: 5px 9px;
      font-size: 12px;
    }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .grid {{ display: grid; gap: 14px; }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }}
    .stock-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }}
    .stock-code, .stock-source {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
    .chips {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0; }}
    .chip {{ border: 1px solid var(--line); background: var(--panel-2); border-radius: 999px; padding: 3px 8px; font-size: 12px; color: var(--muted); }}
    .chip.number {{ color: var(--number); }}
    .evidence {{ margin-top: 12px; border-top: 1px solid var(--line); padding-top: 12px; }}
    .evidence-head {{ margin-bottom: 8px; }}
    .evidence-actions {{ display: flex; gap: 8px; justify-content: flex-end; align-items: center; margin-top: 8px; }}
    .evidence-meta {{ color: var(--muted); font-size: 12px; margin: 0; }}
    pre {{ white-space: pre-wrap; word-break: break-word; color: var(--muted); background: var(--panel-2); padding: 10px; border-radius: 6px; margin: 8px 0 0; }}
    [hidden] {{ display: none !important; }}
    .stock-highlight {{ color: var(--stock); font-weight: 750; }}
    .term-highlight {{ color: var(--term); font-weight: 750; }}
    .number-highlight {{ color: var(--number); font-weight: 750; text-decoration: underline; text-decoration-thickness: 1.5px; text-underline-offset: 3px; }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>Radar 催化估值线索报告</h1>
    <div class="meta">生成时间：{escape(report.generated_at.isoformat(sep=" ", timespec="seconds"))}</div>
    <div class="meta">窗口：{escape(report.start_time.isoformat(sep=" ", timespec="minutes"))} ~ {escape(report.end_time.isoformat(sep=" ", timespec="minutes"))}</div>
    <div class="meta">催化词条目：{report.total_feed_items}，候选标的：{report.total_candidate_stocks}，估值线索标的：{report.total_stocks}</div>
  </header>
  <section class="grid">
    {cards or '<article class="card">暂无具备估值推演数字证据的催化词标的。</article>'}
  </section>
</main>
<script>
document.addEventListener("click", async (event) => {{
  const viewButton = event.target.closest("[data-view-evidence]");
  if (viewButton) {{
    const block = viewButton.closest(".evidence");
    const preview = block?.querySelector(".evidence-preview");
    const full = block?.querySelector(".evidence-full");
    if (!preview || !full) return;
    const expanded = viewButton.getAttribute("aria-expanded") === "true";
    preview.hidden = !expanded;
    full.hidden = expanded;
    viewButton.setAttribute("aria-expanded", String(!expanded));
    viewButton.textContent = expanded ? "查看原文" : "收起原文";
    return;
  }}
  const button = event.target.closest("[data-copy-evidence]");
  if (!button) return;
  const block = button.closest(".evidence");
  const text = block?.querySelector(".evidence-full")?.textContent || "";
  if (!text) return;
  await navigator.clipboard.writeText(text);
  const oldText = button.textContent;
  button.textContent = "已复制";
  window.setTimeout(() => {{ button.textContent = oldText; }}, 1200);
}});
</script>
</body>
</html>
"""


def _stock_card(context: CatalystValuationStockContext) -> str:
    first_evidence = _first_evidence(context)
    return f"""<article class="card">
  <div class="stock-head">
    <div>
      <h2>{escape(context.stock_name)}</h2>
      <div class="stock-code">{escape(context.ts_code or context.stock_key)}</div>
      <div class="stock-source">{escape(_stock_source_line(context, first_evidence))}</div>
    </div>
    <div class="meta">证据 {len(context.evidence)} 条</div>
  </div>
  <div class="chips">{_chips(_all_terms(context))}{_number_chips(_all_numbers(context))}</div>
  <h3>原文证据</h3>
  {''.join(_evidence_html(item, context) for item in context.evidence[:12])}
</article>"""


def _chips(values: list[str]) -> str:
    return "".join(f'<span class="chip">{escape(value)}</span>' for value in values)


def _number_chips(values: list[str]) -> str:
    return "".join(f'<span class="chip number">{escape(value)}</span>' for value in values[:12])


def _first_evidence(context: CatalystValuationStockContext) -> CatalystValuationEvidence | None:
    return min(context.evidence, key=lambda item: item.message_time, default=None)


def _stock_source_line(
    context: CatalystValuationStockContext,
    evidence: CatalystValuationEvidence | None,
) -> str:
    if evidence is None:
        return f"首提：{_time_text(context.first_message_time)}"
    return f"首提：{_time_text(evidence.message_time)} · {_speaker_text(evidence)}"


def _evidence_html(evidence: CatalystValuationEvidence, context: CatalystValuationStockContext) -> str:
    duplicate_text = f" · 合并 {evidence.duplicate_count} 条" if evidence.duplicate_count > 1 else ""
    return f"""<div class="evidence">
  <div class="evidence-head">
    <p class="evidence-meta">{escape(_time_text(evidence.message_time))} · {escape(_speaker_text(evidence))}{escape(duplicate_text)}</p>
  </div>
  <pre class="evidence-preview">{_highlight_evidence(_preview_content(evidence.content), evidence, context)}</pre>
  <pre class="evidence-full" hidden>{_highlight_evidence(evidence.content, evidence, context)}</pre>
  <div class="evidence-actions">
    <button type="button" data-view-evidence aria-expanded="false">查看原文</button>
    <button type="button" data-copy-evidence>复制</button>
  </div>
</div>"""


def _speaker_text(evidence: CatalystValuationEvidence) -> str:
    parts = [str(evidence.source)]
    if evidence.sender:
        parts.append(evidence.sender)
    if evidence.group_name:
        parts.append(evidence.group_name)
    return " / ".join(parts)


def _time_text(value) -> str:
    return value.strftime("%m-%d %H:%M")


def _all_terms(context: CatalystValuationStockContext) -> list[str]:
    return _unique(term for evidence in context.evidence for term in [*evidence.matched_terms, *evidence.valuation_terms])


def _all_numbers(context: CatalystValuationStockContext) -> list[str]:
    return _unique(number for evidence in context.evidence for number in evidence.valuation_numbers)


def _preview_content(text: str, limit: int = 30) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "....."


def _highlight_evidence(
    text: str,
    evidence: CatalystValuationEvidence,
    context: CatalystValuationStockContext,
) -> str:
    tokens: list[tuple[str, str]] = []
    for value in (context.stock_name, context.ts_code, (context.ts_code or "").split(".")[0]):
        _append_highlight_token(tokens, value, "stock-highlight")
    for value in [*evidence.matched_terms, *evidence.valuation_terms]:
        _append_highlight_token(tokens, value, "term-highlight")
    for value in [*extract_display_numbers(text), *evidence.valuation_numbers]:
        _append_highlight_token(tokens, value, "number-highlight")
    return _highlight_tokens(text, tokens)


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


def _unique(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
