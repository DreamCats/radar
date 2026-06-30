import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Bell, Check, Copy, ExternalLink, Loader2, RefreshCw, X } from "lucide-react";

import {
  fetchCatalystValuationReport,
  fetchCatalystValuationReports,
  sendCatalystValuationReportBark,
} from "../api/radarApi";
import { PageLoadingState } from "../components/PageLoadingState";
import { PanelTitle } from "../components/PanelTitle";
import { formatTime } from "../lib/datetime";
import type {
  CatalystValuationEvidence,
  CatalystValuationReportArchiveDetail,
  CatalystValuationReportArchiveItem,
  CatalystValuationReportData,
  CatalystValuationStockContext,
} from "../types";

const GRANULARITY_OPTIONS = [
  { label: "1 小时", value: 60 },
  { label: "30 分钟", value: 30 },
  { label: "全部", value: 0 },
] as const;
const EVIDENCE_PREVIEW_LIMIT = 150;

export function ValuationCluesPage() {
  const [granularity, setGranularity] = useState<number>(60);
  const [items, setItems] = useState<CatalystValuationReportArchiveItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CatalystValuationReportArchiveDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [barkLoading, setBarkLoading] = useState(false);
  const [barkError, setBarkError] = useState<string | null>(null);

  const selectedItem = useMemo(
    () => items.find((item) => item.report_id === selectedId) ?? null,
    [items, selectedId],
  );

  useEffect(() => {
    void loadReports();
  }, [granularity]);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !event.isComposing) {
        setSelectedId(null);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    let cancelled = false;
    setDetail(null);
    setDetailError(null);
    setCopyState("idle");
    setBarkError(null);
    setDetailLoading(true);
    void fetchCatalystValuationReport(selectedId)
      .then((next) => {
        if (!cancelled) {
          setDetail(next);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setDetailError(err instanceof Error ? err.message : "报告详情加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setDetailLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  async function loadReports() {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchCatalystValuationReports({
        granularity_minutes: granularity || undefined,
        limit: 80,
      });
      setItems(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "报告列表加载失败");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  async function copyReport() {
    if (!detail) {
      return;
    }
    try {
      await copyText(buildCopyText(detail.report, detail.published_url));
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
    window.setTimeout(() => setCopyState("idle"), 1400);
  }

  async function sendBark() {
    if (!detail) {
      return;
    }
    setBarkLoading(true);
    setBarkError(null);
    try {
      const response = await sendCatalystValuationReportBark(detail.report_id);
      setDetail(response.item);
      setItems((current) =>
        current.map((item) =>
          item.report_id === response.item.report_id
            ? {
                ...item,
                bark_sent_at: response.item.bark_sent_at,
                bark_error: response.item.bark_error,
                updated_at: response.item.updated_at,
              }
            : item,
        ),
      );
    } catch (err) {
      setBarkError(err instanceof Error ? err.message : "Bark 发送失败");
    } finally {
      setBarkLoading(false);
    }
  }

  return (
    <section className="valuation-clues-page">
      <div className="valuation-toolbar filter-panel">
        <div className="valuation-segmented" aria-label="报告粒度">
          {GRANULARITY_OPTIONS.map((option) => (
            <button
              className={granularity === option.value ? "active" : ""}
              key={option.value}
              type="button"
              onClick={() => setGranularity(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <button
          className="btn btn-sm valuation-refresh"
          type="button"
          aria-label="刷新报告"
          onClick={() => void loadReports()}
          disabled={loading}
        >
          <RefreshCw size={14} />
          <span>刷新</span>
        </button>
      </div>

      {error && <p className="valuation-error">{error}</p>}

      <section className={loading ? "valuation-list-panel content-panel is-refreshing" : "valuation-list-panel content-panel"}>
        <PanelTitle title="催化估值线索" meta={`${items.length} 份归档报告`} />
        {loading && items.length === 0 ? (
          <PageLoadingState label="读取报告归档" variant="strategy" />
        ) : (
          <div className="valuation-report-list">
            {items.map((item) => (
              <button
                className={item.report_id === selectedId ? "valuation-report-row active" : "valuation-report-row"}
                key={item.report_id}
                type="button"
                onClick={() => setSelectedId(item.report_id)}
              >
                <span className="valuation-row-main">
                  <strong>{formatWindowTitle(item)}</strong>
                  <em>{formatWindowMeta(item)}</em>
                  <span>{stockLine(item)}</span>
                </span>
                <span className="valuation-row-metrics">
                  <Metric value={item.total_stocks} label="标的" />
                  <Metric value={item.total_candidate_stocks} label="候选" />
                  <Metric value={item.total_feed_items} label="条目" />
                </span>
                <span className="valuation-row-state">
                  <StatusPill item={item} />
                  {item.published_url && <ExternalLink size={14} aria-hidden="true" />}
                </span>
              </button>
            ))}
            {!loading && items.length === 0 && <p className="empty-line">当前没有归档报告</p>}
          </div>
        )}
      </section>

      {selectedId && (
        <ReportDrawer
          barkError={barkError}
          barkLoading={barkLoading}
          copyState={copyState}
          detail={detail}
          detailError={detailError}
          detailLoading={detailLoading}
          fallbackItem={selectedItem}
          onClose={() => setSelectedId(null)}
          onCopy={() => void copyReport()}
          onSendBark={() => void sendBark()}
        />
      )}
    </section>
  );
}

function ReportDrawer(props: {
  barkError: string | null;
  barkLoading: boolean;
  copyState: "idle" | "copied" | "failed";
  detail: CatalystValuationReportArchiveDetail | null;
  detailError: string | null;
  detailLoading: boolean;
  fallbackItem: CatalystValuationReportArchiveItem | null;
  onClose: () => void;
  onCopy: () => void;
  onSendBark: () => void;
}) {
  const item = props.detail ?? props.fallbackItem;
  return (
    <div className="valuation-drawer-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) {
        props.onClose();
      }
    }}>
      <aside className="valuation-drawer panel" role="dialog" aria-modal="true" aria-label="催化估值线索详情">
        <header className="valuation-drawer-head">
          <div>
            <span className="eyebrow">{item ? formatGeneratedAt(item) : "报告详情"}</span>
            <h2>{item ? formatWindowTitle(item) : "催化估值线索"}</h2>
          </div>
          <div className="valuation-drawer-actions">
            <button className="valuation-icon-action" type="button" aria-label="复制报告" onClick={props.onCopy} disabled={!props.detail}>
              {props.copyState === "copied" ? <Check size={16} /> : <Copy size={16} />}
            </button>
            {props.detail?.published_url && (
              <a className="valuation-icon-action" href={props.detail.published_url} target="_blank" rel="noreferrer" aria-label="打开 HTML">
                <ExternalLink size={16} />
              </a>
            )}
            <button
              className="valuation-icon-action"
              type="button"
              aria-label="发送 Bark"
              onClick={props.onSendBark}
              disabled={!props.detail || !props.detail.published_url || props.barkLoading}
            >
              {props.barkLoading ? <Loader2 size={16} className="valuation-spin" /> : <Bell size={16} />}
            </button>
            <button className="valuation-icon-action" type="button" aria-label="关闭详情" onClick={props.onClose}>
              <X size={16} />
            </button>
          </div>
        </header>

        {props.copyState === "failed" && <p className="valuation-error">复制失败</p>}
        {props.barkError && <p className="valuation-error">{props.barkError}</p>}
        {props.detailLoading && <PageLoadingState label="读取报告详情" variant="strategy" />}
        {props.detailError && <p className="valuation-empty">{props.detailError}</p>}
        {props.detail && <ReportDetail detail={props.detail} />}
      </aside>
    </div>
  );
}

function ReportDetail({ detail }: { detail: CatalystValuationReportArchiveDetail }) {
  return (
    <div className="valuation-drawer-body">
      <div className="valuation-summary-grid">
        <Metric value={detail.total_stocks} label="估值线索标的" />
        <Metric value={detail.total_candidate_stocks} label="候选标的" />
        <Metric value={detail.total_feed_items} label="催化词条目" />
        <Metric value={detail.granularity_minutes ?? "-"} label="分钟粒度" />
      </div>
      <div className="valuation-report-meta">
        <span>{statusText(detail)}</span>
        <span>{detail.published_url ? "HTML 已上传" : "本地 HTML"}</span>
        <span>{detail.bark_sent_at ? `Bark ${formatTime(detail.bark_sent_at)}` : "Bark 未发送"}</span>
      </div>
      <div className="valuation-stock-list">
        {detail.report.stocks.map((stock) => (
          <StockSection key={stock.stock_key} stock={stock} />
        ))}
        {detail.report.stocks.length === 0 && <p className="valuation-empty">暂无具备估值推演数字证据的催化词标的。</p>}
      </div>
    </div>
  );
}

function StockSection({ stock }: { stock: CatalystValuationStockContext }) {
  const terms = unique(stock.evidence.flatMap((item) => item.valuation_terms.concat(item.matched_terms))).slice(0, 8);
  const numbers = unique(stock.evidence.flatMap((item) => item.valuation_numbers)).slice(0, 8);
  return (
    <article className="valuation-stock-section">
      <header>
        <div>
          <h3>{stock.stock_name}</h3>
          <span>{stock.ts_code ?? stock.stock_key}</span>
        </div>
        <em>{stock.evidence.length} 条证据</em>
      </header>
      <div className="valuation-chip-row">
        {terms.map((term) => (
          <span className="valuation-chip" key={`term-${term}`}>{term}</span>
        ))}
        {numbers.map((number) => (
          <span className="valuation-chip number" key={`number-${number}`}>{number}</span>
        ))}
      </div>
      <div className="valuation-evidence-list">
        {stock.evidence.map((evidence) => (
          <EvidenceBlock evidence={evidence} key={evidence.message_id} stock={stock} />
        ))}
      </div>
    </article>
  );
}

function EvidenceBlock({ evidence, stock }: { evidence: CatalystValuationEvidence; stock: CatalystValuationStockContext }) {
  const [expanded, setExpanded] = useState(false);
  const canExpand = evidence.content.length > EVIDENCE_PREVIEW_LIMIT;
  const content = expanded || !canExpand ? evidence.content : `${evidence.content.slice(0, EVIDENCE_PREVIEW_LIMIT)}...`;
  return (
    <section className="valuation-evidence">
      <header>
        <strong>{evidence.sender}</strong>
        <span>{evidence.group_name ?? evidence.source}</span>
        <time>{formatTime(evidence.message_time)}</time>
      </header>
      <pre>{highlightEvidenceContent(content, evidence, stock)}</pre>
      {canExpand && (
        <div className="valuation-evidence-actions">
          <button type="button" onClick={() => setExpanded((current) => !current)}>
            {expanded ? "收起原文" : "查看原文"}
          </button>
        </div>
      )}
    </section>
  );
}

function Metric({ value, label }: { value: number | string; label: string }) {
  return (
    <span className="valuation-metric">
      <strong>{value}</strong>
      <em>{label}</em>
    </span>
  );
}

function StatusPill({ item }: { item: CatalystValuationReportArchiveItem }) {
  return <span className={`valuation-status-pill status-${item.status}`}>{statusText(item)}</span>;
}

function statusText(item: CatalystValuationReportArchiveItem): string {
  if (item.status === "partial_failed") {
    return "部分失败";
  }
  if (item.status === "skipped") {
    return "无标的";
  }
  if (item.status === "failed") {
    return "失败";
  }
  return item.bark_sent_at ? "已 Bark" : "已生成";
}

function formatWindowTitle(item: CatalystValuationReportArchiveItem): string {
  return `${formatTime(item.start_time).slice(5, 16)} ~ ${formatTime(item.end_time).slice(11, 16)}`;
}

function formatWindowMeta(item: CatalystValuationReportArchiveItem): string {
  const granularity = item.granularity_minutes ? `${item.granularity_minutes}m` : "窗口";
  return `${granularity} · ${formatGeneratedAt(item)}`;
}

function formatGeneratedAt(item: CatalystValuationReportArchiveItem): string {
  return `生成 ${formatTime(item.generated_at).slice(11, 19)}`;
}

function stockLine(item: CatalystValuationReportArchiveItem): string {
  if (item.top_stocks.length === 0) {
    return "暂无标的";
  }
  return item.top_stocks.map((stock) => stock.stock_name).join("、");
}

function buildCopyText(report: CatalystValuationReportData, url?: string | null): string {
  const lines = [
    "Radar 催化估值线索报告",
    `生成时间：${formatTime(report.generated_at)}`,
    `窗口：${formatTime(report.start_time)} ~ ${formatTime(report.end_time)}`,
    `催化词条目：${report.total_feed_items}，候选标的：${report.total_candidate_stocks}，估值线索标的：${report.total_stocks}`,
  ];
  if (url) {
    lines.push(`HTML：${url}`);
  }
  for (const [index, stock] of report.stocks.entries()) {
    lines.push("", `${index + 1}. ${stock.stock_name} ${stock.ts_code ?? stock.stock_key}`);
    for (const evidence of stock.evidence) {
      const numbers = evidence.valuation_numbers.length ? `｜数字：${evidence.valuation_numbers.join("、")}` : "";
      lines.push(`- ${formatTime(evidence.message_time)} ${evidence.sender}${numbers}`);
      lines.push(evidence.content);
    }
  }
  return lines.join("\n");
}

function highlightEvidenceContent(
  text: string,
  evidence: CatalystValuationEvidence,
  stock: CatalystValuationStockContext,
): ReactNode[] {
  const tokens: Array<{ text: string; className: string }> = [];
  appendHighlightToken(tokens, stock.stock_name, "valuation-stock-highlight");
  appendHighlightToken(tokens, stock.ts_code, "valuation-stock-highlight");
  appendHighlightToken(tokens, stock.ts_code?.split(".")[0], "valuation-stock-highlight");
  for (const term of evidence.matched_terms.concat(evidence.valuation_terms)) {
    appendHighlightToken(tokens, term, "valuation-term-highlight");
  }
  for (const number of extractDisplayNumbers(text).concat(evidence.valuation_numbers)) {
    appendHighlightToken(tokens, number, "valuation-number-highlight");
  }
  return highlightTokens(text, tokens);
}

function appendHighlightToken(
  tokens: Array<{ text: string; className: string }>,
  value: string | null | undefined,
  className: string,
): void {
  const text = (value ?? "").trim();
  if (text.length < 2) {
    return;
  }
  const exists = tokens.some((token) => token.text.toLowerCase() === text.toLowerCase() && token.className === className);
  if (!exists) {
    tokens.push({ text, className });
  }
}

function highlightTokens(text: string, tokens: Array<{ text: string; className: string }>): ReactNode[] {
  if (tokens.length === 0) {
    return [text];
  }
  const sortedTokens = [...tokens].sort((left, right) => right.text.length - left.text.length);
  const pieces: ReactNode[] = [];
  let index = 0;
  let key = 0;
  while (index < text.length) {
    const match = sortedTokens
      .map((token) => ({ token, foundAt: text.indexOf(token.text, index) }))
      .filter((item) => item.foundAt >= 0)
      .sort((left, right) => left.foundAt - right.foundAt || right.token.text.length - left.token.text.length)[0];
    if (!match) {
      pieces.push(text.slice(index));
      break;
    }
    if (match.foundAt > index) {
      pieces.push(text.slice(index, match.foundAt));
    }
    const end = match.foundAt + match.token.text.length;
    pieces.push(
      <span className={match.token.className} key={`highlight-${key}`}>
        {text.slice(match.foundAt, end)}
      </span>,
    );
    key += 1;
    index = end;
  }
  return pieces;
}

function extractDisplayNumbers(text: string): string[] {
  const moneyPattern =
    /(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)\s*(?:万亿|亿元|亿|千万|万元|百万|万美元|亿美元|人民币|美元|美金|元|[eE])(?:\s*\/\s*(?:吨|台|套|片|颗|件|公斤|kg|g|w|kw|mw|gw|kwh|mwh|gwh|平|平方米|亩))?/gi;
  const quantityPattern =
    /(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+)\s*(?:万吨|吨|万台|台|万套|套|万片|片|万颗|颗|万件|件|公斤|kg|g|gw|mw|kw|w|gwh|mwh|kwh|亩|平方米|平|条线|条)/gi;
  const percentPattern = /\d+(?:\.\d+)?\s*%/g;
  const multiplePattern = /\d+(?:\.\d+)?\s*(?:倍|x|X)/g;
  return unique([
    ...Array.from(text.matchAll(moneyPattern), (match) => match[0]),
    ...Array.from(text.matchAll(quantityPattern), (match) => match[0]),
    ...Array.from(text.matchAll(percentPattern), (match) => match[0]),
    ...Array.from(text.matchAll(multiplePattern), (match) => match[0]),
  ]);
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) {
    throw new Error("复制失败");
  }
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}
