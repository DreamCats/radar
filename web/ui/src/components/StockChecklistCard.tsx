import {
  AlertTriangle,
  BarChart3,
  Building2,
  FileSearch,
  Gauge,
  ListChecks,
  MessageSquareText,
  ShieldAlert,
} from "lucide-react";
import type { ReactNode } from "react";

export type StockChecklistTone = "ready" | "watch" | "risk" | "missing";

export type StockChecklistMetric = {
  label: string;
  value: string;
  tone?: "up" | "down" | "flat";
};

export type StockChecklistSection = {
  key: string;
  icon: "company" | "logic" | "catalyst" | "finance" | "market" | "risk";
  title: string;
  caption: string;
  status: string;
  tone: StockChecklistTone;
  lines: string[];
  empty: string;
};

export type StockChecklistData = {
  status: string;
  tone: StockChecklistTone;
  summary: string;
  metrics: StockChecklistMetric[];
  sections: StockChecklistSection[];
};

type Props = {
  stockName: string;
  tsCode: string;
  checklist: StockChecklistData;
};

const SECTION_ICONS: Record<StockChecklistSection["icon"], ReactNode> = {
  company: <Building2 size={15} />,
  logic: <MessageSquareText size={15} />,
  catalyst: <Gauge size={15} />,
  finance: <FileSearch size={15} />,
  market: <BarChart3 size={15} />,
  risk: <ShieldAlert size={15} />,
};

export function StockChecklistCard({ stockName, tsCode, checklist }: Props) {
  return (
    <section className="stock-checklist-card" aria-label={`${stockName} 个股核查卡`}>
      <header className="stock-checklist-head">
        <div>
          <span className="stock-checklist-kicker">
            <ListChecks size={15} />
            个股核查卡
          </span>
          <strong>{stockName}</strong>
          <small>{tsCode}</small>
        </div>
        <span className={`stock-checklist-status ${checklist.tone}`}>{checklist.status}</span>
      </header>

      <p className="stock-checklist-summary">{checklist.summary || "暂无一句话核查结论。"}</p>

      <div className="stock-checklist-metrics">
        {checklist.metrics.map((metric) => (
          <article key={metric.label}>
            <span>{metric.label}</span>
            <strong className={metric.tone ? `return-${metric.tone}` : undefined}>{metric.value}</strong>
          </article>
        ))}
      </div>

      <div className="stock-checklist-sections">
        {checklist.sections.map((section) => (
          <ChecklistSection section={section} key={section.key} />
        ))}
      </div>
    </section>
  );
}

function ChecklistSection({ section }: { section: StockChecklistSection }) {
  return (
    <article className={`stock-checklist-section ${section.tone}`}>
      <div className="stock-checklist-section-head">
        <span>{SECTION_ICONS[section.icon] ?? <AlertTriangle size={15} />}</span>
        <div>
          <strong>{section.title}</strong>
          <small>{section.caption}</small>
        </div>
        <em>{section.status}</em>
      </div>
      {section.lines.length ? (
        <ul>
          {section.lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : (
        <p>{section.empty}</p>
      )}
    </article>
  );
}
