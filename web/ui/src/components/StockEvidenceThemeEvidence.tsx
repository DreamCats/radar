import { Network } from "lucide-react";

import type { StockEvidenceChainItem, StockEvidenceThemeContext } from "../types";

export function StockEvidenceThemeEvidence({ item }: { item: StockEvidenceChainItem }) {
  const primary = item.primary_theme;
  const lead = primary ?? item.themes[0] ?? null;
  const isConfirmed = primary !== null && primary !== undefined;

  return (
    <section className="stock-evidence-card stock-evidence-card-theme">
      <div className="stock-evidence-card-head">
        <span>
          <Network size={15} />
        </span>
        <div>
          <strong>是不是主线</strong>
          <small>它属于什么主题，在主题里是核心还是边缘。</small>
        </div>
      </div>

      {lead ? (
        <>
          <div className={`stock-evidence-theme-primary ${isConfirmed ? "confirmed" : "uncertain"}`}>
            <div>
              <strong>{lead.theme_name}</strong>
              <small>{isConfirmed ? "系统选出的主叙事" : "最接近的主题候选，还不能当主线"}</small>
            </div>
            <span className={`stock-evidence-theme-quality ${qualityTone(lead)}`}>{lead.quality_label}</span>
            <span>{formatScore(lead.quality_score)}</span>
            <span>{typeLabel(lead.theme_type)}</span>
            <span>{roleLabel(lead.role)}</span>
            <span>{lead.source_count} 源</span>
            {lead.return_rank_5d && lead.member_count && <span>5日强弱 {lead.return_rank_5d}/{lead.member_count}</span>}
          </div>

          <ThemeQualityNotes theme={lead} />

          {!!item.themes.length && (
            <div className="stock-evidence-theme-list stock-evidence-theme-quality-list">
              {item.themes.slice(0, 5).map((candidate) => (
                <ThemeCandidate key={candidate.theme_id} theme={candidate} active={candidate.theme_id === lead.theme_id} />
              ))}
            </div>
          )}
        </>
      ) : (
        <p className="stock-evidence-empty">暂无自动主题归属，先按个股机会观察。</p>
      )}
    </section>
  );
}

function ThemeCandidate({ theme, active }: { theme: StockEvidenceThemeContext; active: boolean }) {
  const warning = theme.quality_warnings[0] ?? theme.missing_evidence[0] ?? "";
  return (
    <span className={active ? "active" : ""}>
      {theme.theme_name}
      <small>{theme.quality_label}</small>
      {warning && <em>{warning}</em>}
    </span>
  );
}

function ThemeQualityNotes({ theme }: { theme: StockEvidenceThemeContext }) {
  const reasons = dedupe([...theme.quality_reasons, ...theme.quality_warnings]);
  if (!reasons.length) {
    return <p className="stock-evidence-empty">主题质量还缺少可解释依据。</p>;
  }
  return (
    <ul className="stock-evidence-theme-quality-notes">
      {reasons.slice(0, 4).map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

function qualityTone(theme: StockEvidenceThemeContext): string {
  if (theme.quality_score >= 0.72) {
    return "strong";
  }
  if (theme.quality_score >= 0.58) {
    return "medium";
  }
  return "weak";
}

function formatScore(value: number): string {
  return `${Math.round(value * 100)}分`;
}

function roleLabel(role: string): string {
  if (role === "core") {
    return "核心";
  }
  if (role === "elastic") {
    return "弹性";
  }
  return "待确认";
}

function typeLabel(type: string): string {
  if (type === "industry") {
    return "行业";
  }
  if (type === "concept") {
    return "概念";
  }
  if (type === "theme") {
    return "题材";
  }
  return type || "主题";
}

function dedupe(items: string[]): string[] {
  return Array.from(new Set(items.filter(Boolean)));
}
