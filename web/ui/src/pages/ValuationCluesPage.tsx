import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { Bell, Calculator, Check, Copy, ExternalLink, Loader2, RefreshCw, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { createPortal } from "react-dom";

import {
  fetchCatalystValuationReport,
  fetchCatalystValuationReports,
  sendCatalystValuationReportBark,
} from "../api/radarApi";
import { ChatWorkspace } from "../components/ChatWorkspace";
import { useChatController } from "../components/useChatController";
import { PageLoadingState } from "../components/PageLoadingState";
import { PanelTitle } from "../components/PanelTitle";
import { formatTime } from "../lib/datetime";
import { useEscapeToClose } from "../lib/useEscapeToClose";
import { useSwipeToCloseSheet } from "../lib/useSwipeToCloseSheet";
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
const UPSIDE_EVIDENCE_PER_STOCK = 3;
const UPSIDE_EVIDENCE_TEXT_LIMIT = 520;

type UpsideChatDraft = {
  title: string;
  subtitle: string;
  surface: string;
  entityId: string;
  context: Array<{ label: string; value: string | number }>;
  evidence: string[];
  draft: string;
};

type UpsideChatRunTarget = {
  title: string;
  subtitle: string;
  surface: string;
  entityId: string;
  runId: string;
  sessionId: string;
  status: NonNullable<CatalystValuationReportArchiveItem["upside_chat_status"]>;
  updatedAt?: string | null;
  error?: string | null;
};

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
  const [upsideDraft, setUpsideDraft] = useState<UpsideChatDraft | null>(null);
  const [upsideRun, setUpsideRun] = useState<UpsideChatRunTarget | null>(null);

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
          setItems((current) =>
            current.map((item) => (item.report_id === next.report_id ? { ...item, ...upsideFields(next) } : item)),
          );
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
                ...upsideFields(response.item),
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

  function openUpsideTask() {
    if (!detail) {
      return;
    }
    setUpsideDraft(buildUpsideChatDraft(detail));
  }

  function openUpsideRun(item: CatalystValuationReportArchiveItem) {
    const target = buildUpsideRunTarget(item);
    if (target) {
      setUpsideRun(target);
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

      <section
        className={loading ? "valuation-list-panel content-panel is-refreshing" : "valuation-list-panel content-panel"}
      >
        <PanelTitle title="催化估值线索" meta={`${items.length} 份归档报告`} />
        {loading && items.length === 0 ? (
          <PageLoadingState label="读取报告归档" variant="strategy" />
        ) : (
          <div className="valuation-report-list">
            {items.map((item) => (
              <ReportRow
                active={item.report_id === selectedId}
                item={item}
                key={item.report_id}
                onOpenUpsideRun={openUpsideRun}
                onSelect={() => setSelectedId(item.report_id)}
              />
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
          onOpenUpside={openUpsideTask}
          onOpenUpsideRun={openUpsideRun}
        />
      )}
      {upsideDraft ? <ReportUpsideChatDrawer draft={upsideDraft} onClose={() => setUpsideDraft(null)} /> : null}
      {upsideRun ? <ReportUpsideRunDrawer run={upsideRun} onClose={() => setUpsideRun(null)} /> : null}
    </section>
  );
}

function ReportRow(props: {
  active: boolean;
  item: CatalystValuationReportArchiveItem;
  onOpenUpsideRun: (item: CatalystValuationReportArchiveItem) => void;
  onSelect: () => void;
}) {
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.target !== event.currentTarget) {
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    event.preventDefault();
    props.onSelect();
  }

  return (
    <article
      className={props.active ? "valuation-report-row active" : "valuation-report-row"}
      onClick={props.onSelect}
      onKeyDown={onKeyDown}
      role="button"
      tabIndex={0}
    >
      <span className="valuation-row-main">
        <strong>{formatWindowTitle(props.item)}</strong>
        <em>{formatWindowMeta(props.item)}</em>
        <span>{stockLine(props.item)}</span>
      </span>
      <span className="valuation-row-metrics">
        <Metric value={props.item.total_stocks} label="标的" />
        <Metric value={props.item.total_candidate_stocks} label="候选" />
        <Metric value={props.item.total_feed_items} label="条目" />
      </span>
      <span className="valuation-row-state">
        <StatusPill item={props.item} />
        <UpsideStatusAction item={props.item} onOpen={props.onOpenUpsideRun} />
        {props.item.published_url && <ExternalLink size={14} aria-hidden="true" />}
      </span>
    </article>
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
  onOpenUpside: () => void;
  onOpenUpsideRun: (item: CatalystValuationReportArchiveItem) => void;
  onSendBark: () => void;
}) {
  const item = props.detail ?? props.fallbackItem;
  const upsideRun = item ? buildUpsideRunTarget(item) : null;
  const upsideActionLabel = upsideRun && item ? upsideActionText(item) : "空间测算";
  const swipeClose = useSwipeToCloseSheet(props.onClose);
  useEscapeToClose(props.onClose, { ignoreWhenSelector: ".chat-launcher-shell" });
  return (
    <div className="valuation-drawer-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) {
        props.onClose();
      }
    }}>
      <aside className="valuation-drawer panel" role="dialog" aria-modal="true" aria-label="催化估值线索详情">
        <header className="valuation-drawer-head" {...swipeClose}>
          <div className="valuation-drawer-title">
            <span className="valuation-drawer-generated">{item ? formatGeneratedAt(item) : "报告详情"}</span>
            <h2>{item ? compactWindowTitle(item) : "催化估值线索"}</h2>
          </div>
          <div className="valuation-drawer-actions">
            <button
              className="valuation-icon-action valuation-ai-action"
              type="button"
              aria-label={upsideRun ? "查看测算任务" : "打开空间测算"}
              title={upsideRun ? "查看测算任务" : "空间测算"}
              onClick={() => (upsideRun && item ? props.onOpenUpsideRun(item) : props.onOpenUpside())}
              disabled={!upsideRun && !props.detail}
            >
              <Calculator size={16} />
              <span>{upsideActionLabel}</span>
            </button>
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

function ReportUpsideRunDrawer(props: { run: UpsideChatRunTarget; onClose: () => void }) {
  const subtitle = `${props.run.subtitle} · ${upsideRunStatusText(props.run.status)}`;
  const controller = useChatController(
    {
      title: props.run.title,
      subtitle,
      surface: props.run.surface,
      entityId: props.run.entityId,
      context: [
        { label: "Run", value: compactId(props.run.runId), copyValue: props.run.runId, copyLabel: "复制 run id" },
        {
          label: "Session",
          value: compactId(props.run.sessionId),
          copyValue: props.run.sessionId,
          copyLabel: "复制 session id",
        },
        { label: "状态", value: upsideRunStatusText(props.run.status) },
        { label: "报告", value: props.run.entityId },
      ],
      initialRunId: props.run.runId,
      initialSessionId: props.run.sessionId,
    },
    true,
  );
  useEscapeToClose(props.onClose, { ignoreWhenSelector: ".chat-reading-modal-shell" });

  const overlay = (
    <AnimatePresence>
      <motion.div
        className="chat-launcher-shell"
        role="dialog"
        aria-modal="true"
        aria-label={props.run.title}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.16 }}
      >
        <motion.button
          className="chat-launcher-scrim"
          type="button"
          aria-label="关闭对话"
          onClick={props.onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        />
        <motion.aside
          className="chat-launcher-panel"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
        >
          <ChatWorkspace
            controller={controller}
            title={props.run.title}
            subtitle={subtitle}
            surface={props.run.surface}
            entityId={props.run.entityId}
            onClose={props.onClose}
          />
        </motion.aside>
      </motion.div>
    </AnimatePresence>
  );

  return createPortal(overlay, document.body);
}

function ReportUpsideChatDrawer(props: { draft: UpsideChatDraft; onClose: () => void }) {
  const controller = useChatController(
    {
      title: props.draft.title,
      subtitle: props.draft.subtitle,
      surface: props.draft.surface,
      entityId: props.draft.entityId,
      context: props.draft.context,
      evidence: props.draft.evidence,
      initialDraft: props.draft.draft,
      skipActiveRunRestore: true,
    },
    true,
  );
  useEscapeToClose(props.onClose, { ignoreWhenSelector: ".chat-reading-modal-shell" });

  const overlay = (
    <AnimatePresence>
      <motion.div
        className="chat-launcher-shell"
        role="dialog"
        aria-modal="true"
        aria-label={props.draft.title}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.16 }}
      >
        <motion.button
          className="chat-launcher-scrim"
          type="button"
          aria-label="关闭对话"
          onClick={props.onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        />
        <motion.aside
          className="chat-launcher-panel"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
        >
          <ChatWorkspace
            controller={controller}
            title={props.draft.title}
            subtitle={props.draft.subtitle}
            surface={props.draft.surface}
            entityId={props.draft.entityId}
            evidence={props.draft.evidence}
            onClose={props.onClose}
          />
        </motion.aside>
      </motion.div>
    </AnimatePresence>
  );

  return createPortal(overlay, document.body);
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
        <span>{upsideStatusText(detail)}</span>
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
  const [copied, setCopied] = useState(false);
  const canExpand = evidence.content.length > EVIDENCE_PREVIEW_LIMIT;
  const content = expanded || !canExpand ? evidence.content : `${evidence.content.slice(0, EVIDENCE_PREVIEW_LIMIT)}...`;

  async function copyEvidenceContent() {
    try {
      await copyText(evidence.content);
    } catch {
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <section className="valuation-evidence">
      <header>
        <strong>{evidence.sender}</strong>
        <span>{evidence.group_name ?? evidence.source}</span>
        <time>{formatTime(evidence.message_time)}</time>
      </header>
      <pre>{highlightEvidenceContent(content, evidence, stock)}</pre>
      <div className="valuation-evidence-actions">
        {canExpand && (
          <button type="button" onClick={() => setExpanded((current) => !current)}>
            {expanded ? "收起原文" : "查看原文"}
          </button>
        )}
        <button type="button" onClick={() => void copyEvidenceContent()}>
          {copied ? "已复制" : "复制原文"}
        </button>
      </div>
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

function UpsideStatusAction(props: {
  item: CatalystValuationReportArchiveItem;
  onOpen: (item: CatalystValuationReportArchiveItem) => void;
}) {
  const target = buildUpsideRunTarget(props.item);
  if (!target) {
    return (
      <span className="valuation-upside-pill idle">
        <Calculator size={12} />
        {upsideStatusText(props.item)}
      </span>
    );
  }
  return (
    <button
      className={`valuation-upside-pill status-${target.status}`}
      title="查看空间测算任务"
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        props.onOpen(props.item);
      }}
    >
      <Calculator size={12} />
      {upsideActionText(props.item)}
    </button>
  );
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

function upsideStatusText(item: CatalystValuationReportArchiveItem): string {
  if (item.upside_chat_status === "running") {
    return "测算中";
  }
  if (item.upside_chat_status === "completed") {
    return "测算完成";
  }
  if (item.upside_chat_status === "failed") {
    return "测算失败";
  }
  if (item.upside_chat_status === "cancelled") {
    return "测算停止";
  }
  return "未测算";
}

function upsideRunStatusText(status: NonNullable<CatalystValuationReportArchiveItem["upside_chat_status"]>): string {
  if (status === "running") {
    return "测算中";
  }
  if (status === "completed") {
    return "测算完成";
  }
  if (status === "failed") {
    return "测算失败";
  }
  return "测算停止";
}

function upsideActionText(item: CatalystValuationReportArchiveItem): string {
  if (item.upside_chat_status === "running") {
    return "继续测算";
  }
  if (item.upside_chat_status === "failed") {
    return "查看失败";
  }
  if (item.upside_chat_status === "cancelled") {
    return "查看停止";
  }
  return "查看测算";
}

function formatWindowTitle(item: CatalystValuationReportArchiveItem): string {
  return `${formatTime(item.start_time).slice(5, 16)} ~ ${formatTime(item.end_time).slice(11, 16)}`;
}

function compactWindowTitle(item: CatalystValuationReportArchiveItem): string {
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

function buildUpsideRunTarget(item: CatalystValuationReportArchiveItem): UpsideChatRunTarget | null {
  if (!item.upside_chat_run_id || !item.upside_chat_session_id || !item.upside_chat_status) {
    return null;
  }
  return {
    title: "估值线索空间测算",
    subtitle: `${formatWindowTitle(item)} · ${item.total_stocks} 标的`,
    surface: "估值线索",
    entityId: item.report_id,
    runId: item.upside_chat_run_id,
    sessionId: item.upside_chat_session_id,
    status: item.upside_chat_status,
    updatedAt: item.upside_chat_updated_at,
    error: item.upside_chat_error,
  };
}

function upsideFields(item: CatalystValuationReportArchiveItem): Partial<CatalystValuationReportArchiveItem> {
  return {
    upside_chat_run_id: item.upside_chat_run_id,
    upside_chat_session_id: item.upside_chat_session_id,
    upside_chat_status: item.upside_chat_status,
    upside_chat_updated_at: item.upside_chat_updated_at,
    upside_chat_error: item.upside_chat_error,
  };
}

function compactId(value: string): string {
  return value.length <= 12 ? value : `${value.slice(0, 8)}...${value.slice(-4)}`;
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

function buildUpsideChatDraft(detail: CatalystValuationReportArchiveDetail): UpsideChatDraft {
  const title = "估值线索空间测算";
  const subtitle = `${formatWindowTitle(detail)} · ${detail.total_stocks} 标的`;
  const reportUrl = detail.published_url ?? "";
  const stockNames = detail.report.stocks.map((stock) => `${stock.stock_name}${stock.ts_code ? ` ${stock.ts_code}` : ""}`);
  return {
    title,
    subtitle,
    surface: "估值线索",
    entityId: detail.report_id,
    context: [
      { label: "报告", value: detail.report_id },
      { label: "报告窗口", value: `${formatTime(detail.start_time)} ~ ${formatTime(detail.end_time)}` },
      { label: "生成时间", value: formatTime(detail.generated_at) },
      { label: "HTML", value: reportUrl || "未上传" },
      { label: "标的", value: stockNames.join("、") || "无" },
      { label: "标的数量", value: detail.total_stocks },
      { label: "催化词条目", value: detail.total_feed_items },
    ],
    evidence: buildUpsideEvidence(detail.report),
    draft: buildUpsidePrompt(detail, stockNames),
  };
}

function buildUpsidePrompt(detail: CatalystValuationReportArchiveDetail, stockNames: string[]): string {
  return [
    "请先调用 radar_load_skill 读取 catalyst-valuation-upside，再调用 radar_get_catalyst_valuation_report 读取这份本地结构化报告，然后做空间测算。",
    "",
    "任务要求：",
    "1. 使用 report_id 读取报告数据，不要依赖公网报告 URL 抓网页正文。",
    "2. 对报告里的每个标的补当前市值：优先用 radar_get_stock_price_history 查询 daily_basic 最近交易日 total_mv；必要时用 radar_get_realtime_quote 补盘中价格/涨跌幅。",
    "3. 在“原文证据成立”的假设下，用第一性原理重算目标市值区间；不要只复述报告里的数字。",
    "4. 计算剩余空间，并标记：显著空间 / 有空间但需验证 / 基本反映 / 已超目标 / 严重透支。",
    "5. 把已确认事实、基于假设的推断、仍需验证条件分开写。",
    "6. 输出机会排序、追高风险、关键数据缺口；不要输出买卖建议、仓位或确定性收益。",
    "",
    `report_id：${detail.report_id}`,
    `报告窗口：${formatTime(detail.start_time)} ~ ${formatTime(detail.end_time)}`,
    `报告 URL：${detail.published_url ?? "未上传"}`,
    `标的列表：${stockNames.join("、") || "无"}`,
  ].join("\n");
}

function buildUpsideEvidence(report: CatalystValuationReportData): string[] {
  return report.stocks.flatMap((stock) =>
    stock.evidence.slice(0, UPSIDE_EVIDENCE_PER_STOCK).map((evidence) => {
      const source = evidence.group_name ?? evidence.source;
      const terms = unique(evidence.valuation_terms.concat(evidence.matched_terms)).join("、") || "无";
      const numbers = evidence.valuation_numbers.join("、") || "无";
      const content = clipText(evidence.content, UPSIDE_EVIDENCE_TEXT_LIMIT);
      return [
        `${stock.stock_name} ${stock.ts_code ?? stock.stock_key}`,
        `时间：${formatTime(evidence.message_time)}；发送人：${evidence.sender}；来源：${source}`,
        `命中词：${terms}；数字：${numbers}`,
        `原文：${content}`,
      ].join("\n");
    }),
  );
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

function clipText(text: string, limit: number): string {
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length <= limit ? compact : `${compact.slice(0, limit)}...`;
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
