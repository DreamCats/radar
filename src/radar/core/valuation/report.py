from __future__ import annotations

import re
from datetime import datetime
from html import escape
from pathlib import Path

from radar.core.cloud import upload_aly
from radar.core.config import RadarConfig
from radar.core.storage.valuation_store import ValuationMeasurement, ValuationMeasurementItem


def write_valuation_measurement_html(
    config: RadarConfig,
    measurement: ValuationMeasurement,
    *,
    session_markdown: str,
    source_report_url: str | None,
    output_path: Path | None = None,
) -> Path:
    path = output_path or _default_output_path(config, measurement)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_valuation_measurement_html(
            measurement,
            session_markdown=session_markdown,
            source_report_url=source_report_url,
        ),
        encoding="utf-8",
    )
    return path


def publish_valuation_measurement_html(
    config: RadarConfig,
    local_path: Path,
    *,
    measurement: ValuationMeasurement,
) -> str:
    measured_at = measurement.measured_at
    remote_path = f"valuation-measurement/{measured_at:%Y%m%d-%H%M%S}-{measurement.measurement_id[-8:]}.html"
    return upload_aly(config, local_path, remote_path).url


def render_valuation_measurement_html(
    measurement: ValuationMeasurement,
    *,
    session_markdown: str,
    source_report_url: str | None,
) -> str:
    positives = [item for item in measurement.items if item.is_positive]
    rows = "\n".join(_item_row(item) for item in measurement.items)
    cards = "\n".join(_positive_card(item) for item in positives)
    source_link = (
        f'<a class="link" href="{escape(source_report_url, quote=True)}">来源估值线索报告</a>'
        if source_report_url
        else '<span class="muted">来源估值线索报告未上传</span>'
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Radar 估值测算报告</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07080b;
      --panel: #12151b;
      --panel-2: #191d25;
      --text: #eef2f8;
      --muted: #9aa5b5;
      --line: #2a303b;
      --accent: #34d399;
      --warn: #fbbf24;
      --bad: #f87171;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 28px 16px 48px; }}
    header {{ margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; letter-spacing: 0; }}
    .meta, .muted {{ color: var(--muted); font-size: 13px; }}
    .summary {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 16px 0; }}
    .metric, .card, .markdown {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 20px; }}
    .grid {{ display: grid; gap: 12px; }}
    .card h3 {{ margin: 0 0 6px; font-size: 17px; }}
    .card-line {{ color: var(--muted); margin: 4px 0; }}
    .upside {{ color: var(--accent); font-weight: 750; }}
    .status {{ color: var(--warn); }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }}
    table {{ width: 100%; min-width: 760px; border-collapse: collapse; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ color: var(--muted); background: var(--panel-2); font-weight: 650; }}
    tr:last-child td {{ border-bottom: 0; }}
    section {{ margin-top: 22px; }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
      color: #d9e2ef;
    }}
    .markdown {{ background: #101319; }}
    .markdown h3, .markdown h4 {{ margin: 18px 0 8px; letter-spacing: 0; }}
    .markdown h3:first-child, .markdown h4:first-child {{ margin-top: 0; }}
    .markdown h3 {{ font-size: 18px; }}
    .markdown h4 {{ font-size: 15px; color: #dbe4f0; }}
    .markdown p {{ margin: 10px 0; }}
    .markdown ul, .markdown ol {{ margin: 10px 0; padding-left: 22px; }}
    .markdown li {{ margin: 6px 0; }}
    .markdown strong {{ color: #f8fafc; font-weight: 760; }}
    .markdown code {{
      border: 1px solid var(--line);
      border-radius: 5px;
      background: #0b0d12;
      padding: 1px 5px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92em;
    }}
    .markdown pre {{
      margin: 12px 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0b0d12;
      overflow-x: auto;
    }}
    .markdown pre code {{ border: 0; padding: 0; background: transparent; }}
    .markdown-table-wrap {{
      margin: 12px 0;
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .markdown-table-wrap table {{ min-width: 860px; }}
    .markdown blockquote {{
      margin: 12px 0;
      padding: 8px 12px;
      border-left: 3px solid var(--accent);
      background: rgba(52, 211, 153, 0.08);
      color: #dbe4f0;
    }}
    .markdown hr {{ border: 0; border-top: 1px solid var(--line); margin: 18px 0; }}
    .link {{ color: #38bdf8; text-decoration: none; }}
    .source {{ margin-top: 10px; }}
    @media (max-width: 720px) {{
      main {{ padding: 22px 12px 40px; }}
      .summary {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>Radar 估值测算报告</h1>
    <div class="meta">测算时间：{escape(_time_text(measurement.measured_at))}</div>
    <div class="meta">来源报告：{escape(measurement.report_id)}</div>
    <div class="source">{source_link}</div>
  </header>
  <div class="summary">
    <div class="metric"><span>测算标的</span><strong>{measurement.total_items}</strong></div>
    <div class="metric"><span>正向空间</span><strong>{measurement.positive_count}</strong></div>
    <div class="metric"><span>解析状态</span><strong>{escape(measurement.parse_status)}</strong></div>
  </div>
  <section>
    <h2>正向标的</h2>
    <div class="grid">{cards or '<article class="card muted">暂无正向空间标的。</article>'}</div>
  </section>
  <section>
    <h2>结构化总表</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>标的</th>
            <th>当前市值</th>
            <th>目标市值</th>
            <th>剩余空间</th>
            <th>状态</th>
            <th>确定性</th>
            <th>关键验证</th>
          </tr>
        </thead>
        <tbody>{rows or '<tr><td colspan="7" class="muted">暂无结构化条目。</td></tr>'}</tbody>
      </table>
    </div>
  </section>
  <section>
    <h2>完整 Session Markdown</h2>
    <div class="markdown">{_render_markdown(session_markdown.strip() or "暂无内容")}</div>
  </section>
</main>
</body>
</html>
"""


def _item_row(item: ValuationMeasurementItem) -> str:
    name = _item_title(item)
    return f"""<tr>
  <td>{escape(name)}</td>
  <td>{escape(item.current_mv_text or "-")}</td>
  <td>{escape(item.target_mv_text or "-")}</td>
  <td class="upside">{escape(item.upside_text or "-")}</td>
  <td>{escape(item.valuation_status or "-")}</td>
  <td>{escape(item.confidence or "-")}</td>
  <td>{escape(item.key_validation or "-")}</td>
</tr>"""


def _positive_card(item: ValuationMeasurementItem) -> str:
    return f"""<article class="card">
  <h3>{escape(_item_title(item))}</h3>
  <p class="card-line"><span class="upside">{escape(item.upside_text or "空间未列明")}</span> · <span class="status">{escape(item.valuation_status or "状态未列明")}</span> · 确定性 {escape(item.confidence or "-")}</p>
  <p class="card-line">当前：{escape(item.current_mv_text or "-")}；目标：{escape(item.target_mv_text or "-")}</p>
  <p class="card-line">验证：{escape(item.key_validation or "-")}</p>
</article>"""


def _item_title(item: ValuationMeasurementItem) -> str:
    return f"{item.name} {item.ts_code}" if item.ts_code else item.name


def _default_output_path(config: RadarConfig, measurement: ValuationMeasurement) -> Path:
    measured_at = measurement.measured_at
    return config.data_dir / "valuation_measurement" / f"{measured_at:%Y%m%d-%H%M%S}-{measurement.measurement_id[-8:]}.html"


def _time_text(value: datetime) -> str:
    return value.isoformat(sep=" ", timespec="minutes")


def _render_markdown(content: str) -> str:
    blocks: list[str] = []
    pattern = re.compile(r"```(\w+)?\n([\s\S]*?)```")
    last_index = 0
    for match in pattern.finditer(content):
        if match.start() > last_index:
            blocks.append(_render_markdown_text(content[last_index : match.start()]))
        code = escape(match.group(2).rstrip())
        blocks.append(f"<pre><code>{code}</code></pre>")
        last_index = match.end()
    if last_index < len(content):
        blocks.append(_render_markdown_text(content[last_index:]))
    return "\n".join(block for block in blocks if block)


def _render_markdown_text(content: str) -> str:
    lines = content.splitlines()
    nodes: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if _is_horizontal_rule(line):
            nodes.append("<hr>")
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            tag = "h3" if len(heading.group(1)) <= 2 else "h4"
            nodes.append(f"<{tag}>{_render_inline_markdown(heading.group(2))}</{tag}>")
            index += 1
            continue
        if _is_table_header(lines, index):
            table_html, index = _render_markdown_table(lines, index)
            nodes.append(table_html)
            continue
        if re.match(r"^\s*[-*]\s+", line):
            html, index = _render_markdown_list(lines, index, ordered=False)
            nodes.append(html)
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            html, index = _render_markdown_list(lines, index, ordered=True)
            nodes.append(html)
            continue
        if re.match(r"^>\s?", line):
            quote = re.sub(r"^>\s?", "", line)
            nodes.append(f"<blockquote>{_render_inline_markdown(quote)}</blockquote>")
            index += 1
            continue

        paragraph = [line]
        index += 1
        while index < len(lines) and _continues_paragraph(lines, index):
            paragraph.append(lines[index])
            index += 1
        nodes.append(f"<p>{_render_inline_markdown(' '.join(part.strip() for part in paragraph))}</p>")
    return "\n".join(nodes)


def _continues_paragraph(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not line.strip():
        return False
    return not (
        _is_horizontal_rule(line)
        or re.match(r"^(#{1,6})\s+", line)
        or re.match(r"^\s*[-*]\s+", line)
        or re.match(r"^\s*\d+\.\s+", line)
        or re.match(r"^>\s?", line)
        or _is_table_header(lines, index)
    )


def _render_markdown_list(lines: list[str], start: int, *, ordered: bool) -> tuple[str, int]:
    tag = "ol" if ordered else "ul"
    pattern = r"^\s*\d+\.\s+" if ordered else r"^\s*[-*]\s+"
    items: list[str] = []
    index = start
    while index < len(lines) and re.match(pattern, lines[index]):
        item = re.sub(pattern, "", lines[index])
        items.append(f"<li>{_render_inline_markdown(item)}</li>")
        index += 1
    return f"<{tag}>\n{''.join(items)}\n</{tag}>", index


def _render_markdown_table(lines: list[str], start: int) -> tuple[str, int]:
    headers = _parse_table_row(lines[start])
    rows: list[list[str]] = []
    index = start + 2
    while index < len(lines) and _is_table_row(lines[index]):
        rows.append(_parse_table_row(lines[index]))
        index += 1
    header_html = "".join(f"<th>{_render_inline_markdown(header)}</th>" for header in headers)
    row_html = "".join(
        "<tr>"
        + "".join(
            f"<td>{_render_inline_markdown(row[cell_index] if cell_index < len(row) else '')}</td>"
            for cell_index in range(len(headers))
        )
        + "</tr>"
        for row in rows
    )
    return (
        "<div class=\"markdown-table-wrap\"><table>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{row_html}</tbody>"
        "</table></div>",
        index,
    )


def _is_horizontal_rule(line: str) -> bool:
    return re.match(r"^\s*-{3,}\s*$", line) is not None


def _is_table_header(lines: list[str], index: int) -> bool:
    return (
        _is_table_row(lines[index])
        and index + 1 < len(lines)
        and re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[index + 1])
        is not None
    )


def _is_table_row(line: str) -> bool:
    return "|" in line and len([cell for cell in line.split("|") if cell.strip()]) >= 2


def _parse_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _render_inline_markdown(text: str) -> str:
    safe = escape(text)
    safe = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", safe)
    safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
    return safe
