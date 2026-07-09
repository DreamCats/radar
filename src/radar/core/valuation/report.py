from __future__ import annotations

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
    <div class="markdown"><pre>{escape(session_markdown.strip() or "暂无内容")}</pre></div>
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
