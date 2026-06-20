import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Cable,
  CircleDot,
  Cpu,
  Droplets,
  Fan,
  Gauge,
  GitBranch,
  Network,
  ShieldCheck,
  Target,
  Wind,
} from "lucide-react";

import type {
  IndustryChainCompany,
  IndustryChainData,
  IndustryChainDetail,
  IndustryChainEdge,
  IndustryChainEvidenceStatus,
  IndustryChainFinancialTranslation,
  IndustryChainLearningStep,
  IndustryChainNode,
  IndustryChainConceptDiagram,
} from "../types";

const TIER_FILTERS = [
  { key: "all", label: "全部" },
  { key: "leader", label: "龙头/验证锚" },
  { key: "validation_node", label: "验证节点" },
  { key: "flexible_candidate", label: "弹性候选" },
];

export function IndustryChainHeader({ detail }: { detail: IndustryChainDetail }) {
  const data = detail.data;
  const supportedCount = data.companies.filter((company) => company.evidence_status === "supported").length;
  const candidateCount = data.companies.filter((company) => company.evidence_status === "candidate").length;
  const highImportanceCount = data.nodes.filter((node) => node.bottleneck_strength >= 5).length;

  return (
    <section className="industry-chain-hero-panel">
      <div className="industry-chain-title-block">
        <span className="eyebrow">{data.category}</span>
        <h1>{data.title}</h1>
        <p>{data.summary}</p>
        <div className="industry-chain-tags">
          {detail.item.entry_tags.map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      </div>
      <div className="industry-chain-metrics">
        <MetricTile icon={<Network size={16} />} label="图谱节点" value={data.nodes.length} />
        <MetricTile icon={<GitBranch size={16} />} label="关键关系" value={data.edges.length} />
        <MetricTile icon={<Target size={16} />} label="关键节点" value={highImportanceCount} />
        <MetricTile icon={<ShieldCheck size={16} />} label="强证据公司" value={supportedCount || `${candidateCount} 待核`} />
      </div>
    </section>
  );
}

export function QuickReadPanel({ data }: { data: IndustryChainData }) {
  const quickRead = data.quick_read;
  if (!quickRead) {
    return null;
  }

  return (
    <section className="industry-chain-quick-panel">
      <div className="industry-chain-section-head">
        <div>
          <span className="eyebrow">3 分钟看懂</span>
          <h2>{quickRead.headline}</h2>
        </div>
      </div>
      <p className="industry-chain-quick-summary">{quickRead.summary}</p>
      <div className="industry-chain-logic-chain" aria-label="产业链理解顺序">
        {quickRead.logic_chain.map((item, index) => (
          <div className="industry-chain-logic-step" key={item}>
            <b>{index + 1}</b>
            <span>{item}</span>
          </div>
        ))}
      </div>
      <div className="industry-chain-takeaways">
        {quickRead.takeaways.map((item) => (
          <p key={item}>{item}</p>
        ))}
      </div>
    </section>
  );
}

export function EvidenceGuidePanel({ data }: { data: IndustryChainData }) {
  const labels = data.evidence_policy?.labels ?? [];
  if (!labels.length) {
    return null;
  }

  return (
    <section className="industry-chain-evidence-guide-panel">
      <div className="industry-chain-section-head">
        <div>
          <span className="eyebrow">证据等级</span>
          <h2>先分清事实、线索和待验证</h2>
        </div>
        <ShieldCheck size={16} />
      </div>
      <div className="industry-chain-evidence-guide-grid">
        {labels.map((item) => (
          <div className="industry-chain-evidence-guide-item" key={item.status}>
            <div>
              <EvidenceBadge status={item.status} />
              <strong>{item.meaning}</strong>
            </div>
            <p>{item.evidence_needed}</p>
          </div>
        ))}
      </div>
      {data.evidence_policy?.upgrade_rule && (
        <p className="industry-chain-evidence-rule">{data.evidence_policy.upgrade_rule}</p>
      )}
    </section>
  );
}

export function LearningPathPanel({
  data,
  activeStepId,
  onSelectStep,
}: {
  data: IndustryChainData;
  activeStepId: string;
  onSelectStep: (stepId: string) => void;
}) {
  const steps = data.learning_steps ?? [];
  if (!steps.length) {
    return null;
  }

  return (
    <section className="industry-chain-learning-panel">
      <div className="industry-chain-section-head">
        <div>
          <span className="eyebrow">认知路径</span>
          <h2>先看远因，再拆卡点，最后验证公司</h2>
        </div>
      </div>
      <div className="industry-chain-learning-steps">
        {steps.map((step, index) => (
          <button
            className={step.id === activeStepId ? "active" : ""}
            type="button"
            key={step.id}
            onClick={() => onSelectStep(step.id)}
          >
            <b>{index + 1}</b>
            <span>{step.title}</span>
            <em>{step.subtitle}</em>
          </button>
        ))}
      </div>
    </section>
  );
}

export function NodeDetailPanel({
  activeStep,
  node,
  edges,
  companies,
}: {
  activeStep: IndustryChainLearningStep | null;
  node: IndustryChainNode | null;
  edges: IndustryChainEdge[];
  companies: IndustryChainCompany[];
}) {
  if (!node) {
    return null;
  }

  return (
    <aside className="industry-chain-node-panel">
      {activeStep && (
        <div className="industry-chain-step-brief">
          <span className="eyebrow">这一层先回答</span>
          <strong>{activeStep.question}</strong>
          <p>{activeStep.answer}</p>
        </div>
      )}
      <div className="industry-chain-section-head">
        <div>
          <span className="eyebrow">当前节点</span>
          <h2>{node.label}</h2>
        </div>
        <EvidenceBadge status={node.evidence_status} />
      </div>
      <p className="industry-chain-node-explain">{node.beginner_explanation}</p>
      <NodeTeachingCard node={node} />
      <div className="industry-chain-importance">
        <div className="industry-chain-importance-head">
          <span>产业链关键度</span>
          <strong>{node.bottleneck_strength}/5</strong>
        </div>
        <div className="industry-chain-bottleneck-meter" aria-label={`产业链关键度 ${node.bottleneck_strength}/5`}>
          {Array.from({ length: 5 }, (_, index) => (
            <span className={index < node.bottleneck_strength ? "active" : ""} key={index} />
          ))}
        </div>
        <p>用于判断这个节点对理解链路是否关键，不代表证据强弱。</p>
      </div>
      <div className="industry-chain-node-meta">
        <span>层级：{layerLabel(node.layer)}</span>
        <span>分组：{groupLabel(node.group)}</span>
      </div>
      <NodeRelations edges={edges} />
      <div className="industry-chain-node-section">
        <strong>相关公司</strong>
        {companies.length ? (
          <div className="industry-chain-related-company-list">
            {companies.map((company) => (
              <span key={company.ts_code}>{company.name}</span>
            ))}
          </div>
        ) : (
          <p>暂无 A 股映射。</p>
        )}
      </div>
    </aside>
  );
}

function NodeTeachingCard({ node }: { node: IndustryChainNode }) {
  const teach = node.teach;
  if (!teach) {
    return null;
  }

  return (
    <div className="industry-chain-node-teach">
      <TeachingLine title="它是什么" value={teach.what} />
      <TeachingLine title="为什么重要" value={teach.why_matters} />
      <TeachingLine title="怎么受益" value={teach.benefit_logic} />
      <div className="industry-chain-teach-watch">
        <span>重点看</span>
        <div>
          {teach.watch.map((item) => (
            <em key={item}>{item}</em>
          ))}
        </div>
      </div>
      <TeachingLine title="常见误区" value={teach.common_misread} />
    </div>
  );
}

function TeachingLine({ title, value }: { title: string; value: string }) {
  return (
    <div className="industry-chain-teach-line">
      <span>{title}</span>
      <p>{value}</p>
    </div>
  );
}

function NodeRelations({ edges }: { edges: IndustryChainEdge[] }) {
  return (
    <div className="industry-chain-node-section">
      <strong>相关关系</strong>
      {edges.length ? (
        edges.map((edge) => (
          <p key={`${edge.source}-${edge.target}`}>
            <CircleDot size={12} />
            {edge.label}：{edge.description}
          </p>
        ))
      ) : (
        <p>暂无结构化关系。</p>
      )}
    </div>
  );
}

export function ConceptDiagramPanel({
  data,
  onSelectNode,
}: {
  data: IndustryChainData;
  onSelectNode: (nodeId: string) => void;
}) {
  const diagrams = data.concept_diagrams ?? [];
  const nodesById = useMemo(() => new Map(data.nodes.map((node) => [node.id, node])), [data.nodes]);
  if (!diagrams.length) {
    return null;
  }

  return (
    <section className="industry-chain-concept-panel">
      <div className="industry-chain-section-head">
        <div>
          <span className="eyebrow">术语图解</span>
          <h2>先把专业词变成直观画面</h2>
        </div>
        <BookOpen size={16} />
      </div>
      <div className="industry-chain-concept-grid">
        {diagrams.map((diagram) => (
          <ConceptDiagramCard
            diagram={diagram}
            key={diagram.id}
            nodesById={nodesById}
            onSelectNode={onSelectNode}
          />
        ))}
      </div>
    </section>
  );
}

function ConceptDiagramCard({
  diagram,
  nodesById,
  onSelectNode,
}: {
  diagram: IndustryChainConceptDiagram;
  nodesById: Map<string, IndustryChainNode>;
  onSelectNode: (nodeId: string) => void;
}) {
  return (
    <article className="industry-chain-concept-card">
      <div className="industry-chain-concept-card-head">
        <span>{diagramIcon(diagram.icon)}</span>
        <div>
          <strong>{diagram.title}</strong>
          <p>{diagram.subtitle}</p>
        </div>
      </div>
      <div className="industry-chain-concept-flow" aria-label={`${diagram.title}流程`}>
        {diagram.parts.map((part, index) => (
          <Fragment key={`${diagram.id}-${part.label}`}>
            <div className="industry-chain-concept-part">
              <span>{part.role}</span>
              <strong>{part.label}</strong>
              <p>{part.description}</p>
            </div>
            {index < diagram.parts.length - 1 && (
              <span className="industry-chain-concept-arrow" aria-hidden="true">
                <ArrowRight size={15} />
              </span>
            )}
          </Fragment>
        ))}
      </div>
      <p className="industry-chain-concept-takeaway">{diagram.takeaway}</p>
      <div className="industry-chain-node-tags">
        {diagram.node_ids.map((nodeId) => (
          <button type="button" key={nodeId} onClick={() => onSelectNode(nodeId)}>
            {nodesById.get(nodeId)?.label ?? nodeId}
          </button>
        ))}
      </div>
    </article>
  );
}

function diagramIcon(icon: IndustryChainConceptDiagram["icon"]) {
  switch (icon) {
    case "wind":
      return <Wind size={18} />;
    case "liquid":
      return <Droplets size={18} />;
    case "chip":
      return <Cpu size={18} />;
    case "control":
      return <Gauge size={18} />;
    case "connector":
      return <Cable size={18} />;
    case "system":
      return <Network size={18} />;
    default:
      return <Fan size={18} />;
  }
}

export function CompanyRolePanel({
  companies,
  data,
  selectedNode,
  tier,
  onSetTier,
  onSelectNode,
}: {
  companies: IndustryChainCompany[];
  data: IndustryChainData;
  selectedNode: IndustryChainNode | null;
  tier: string;
  onSetTier: (tier: string) => void;
  onSelectNode: (nodeId: string) => void;
}) {
  const nodesById = useMemo(() => new Map(data.nodes.map((node) => [node.id, node])), [data.nodes]);
  const financialByNode = useMemo(
    () => new Map((data.financial_translations ?? []).map((item) => [item.node_id, item])),
    [data.financial_translations],
  );
  const [selectedCompanyCode, setSelectedCompanyCode] = useState(companies[0]?.ts_code ?? "");
  const selectedCompany = companies.find((company) => company.ts_code === selectedCompanyCode) ?? companies[0] ?? null;

  useEffect(() => {
    if (!companies.length) {
      setSelectedCompanyCode("");
      return;
    }
    if (!companies.some((company) => company.ts_code === selectedCompanyCode)) {
      setSelectedCompanyCode(companies[0].ts_code);
    }
  }, [companies, selectedCompanyCode]);

  return (
    <section className="industry-chain-company-panel">
      <div className="industry-chain-section-head">
        <div>
          <span className="eyebrow">A 股映射</span>
          <h2>先看角色，再补证据</h2>
        </div>
        <div className="industry-chain-segmented" role="tablist" aria-label="公司分层">
          {TIER_FILTERS.map((filter) => (
            <button
              className={tier === filter.key ? "active" : ""}
              type="button"
              role="tab"
              aria-selected={tier === filter.key}
              key={filter.key}
              onClick={() => onSetTier(filter.key)}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>
      <div className="industry-chain-company-workspace">
        <div className="industry-chain-company-list" aria-label="公司列表" role="listbox">
          {companies.map((company) => (
            <CompanyListItem
              active={selectedCompany?.ts_code === company.ts_code}
              company={company}
              key={company.ts_code}
              related={Boolean(selectedNode && company.nodes.includes(selectedNode.id))}
              onSelect={() => setSelectedCompanyCode(company.ts_code)}
            />
          ))}
        </div>
        {selectedCompany ? (
          <CompanyDetailCard
            company={selectedCompany}
            financialByNode={financialByNode}
            nodesById={nodesById}
            onSelectNode={onSelectNode}
          />
        ) : (
          <p className="industry-chain-company-empty">当前筛选下暂无公司。</p>
        )}
      </div>
    </section>
  );
}

function CompanyListItem({
  active,
  company,
  related,
  onSelect,
}: {
  active: boolean;
  company: IndustryChainCompany;
  related: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={[
        "industry-chain-company-row",
        active ? "active" : "",
        related ? "related" : "",
        company.attention_level ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      type="button"
      role="option"
      aria-selected={active}
      onClick={onSelect}
    >
      <span className="industry-chain-company-row-head">
        <strong>{company.name}</strong>
        <em>{company.ts_code}</em>
      </span>
      <span className="industry-chain-company-row-badges">
        <AttentionBadge company={company} />
        <EvidenceBadge status={company.evidence_status} />
      </span>
      <span className="industry-chain-company-row-role">{company.role}</span>
      <span className="industry-chain-company-row-view">{company.current_view}</span>
    </button>
  );
}

function CompanyDetailCard({
  company,
  financialByNode,
  nodesById,
  onSelectNode,
}: {
  company: IndustryChainCompany;
  financialByNode: Map<string, IndustryChainFinancialTranslation>;
  nodesById: Map<string, IndustryChainNode>;
  onSelectNode: (nodeId: string) => void;
}) {
  const financialChecks = company.nodes
    .map((nodeId) => financialByNode.get(nodeId))
    .filter((item): item is IndustryChainFinancialTranslation => Boolean(item))
    .slice(0, 2);

  return (
    <article className="industry-chain-company-detail-card">
      <div className="industry-chain-company-card-head">
        <div>
          <strong>{company.name}</strong>
          <span>{company.ts_code}</span>
        </div>
        <div className="industry-chain-company-card-badges">
          <AttentionBadge company={company} />
          <EvidenceBadge status={company.evidence_status} />
        </div>
      </div>
      <p className="industry-chain-company-detail-subtitle">个股详情分析</p>
      <CompanyCardSection title="角色">
        <p>{company.role}</p>
        {company.leader_reason && <small>{company.leader_reason}</small>}
      </CompanyCardSection>
      {company.why_watch && (
        <CompanyCardSection title="为什么值得看">
          <p>{company.why_watch}</p>
        </CompanyCardSection>
      )}
      <CompanyCardSection title="对应链路">
        <div className="industry-chain-node-tags">
          {company.nodes.map((nodeId) => (
            <button type="button" key={nodeId} onClick={() => onSelectNode(nodeId)}>
              {nodesById.get(nodeId)?.label ?? nodeId}
            </button>
          ))}
        </div>
      </CompanyCardSection>
      <CompanyCardSection title="当前证据">
        <em>{company.current_view}</em>
      </CompanyCardSection>
      <CompanyListSection title="证据依据" items={company.evidence_basis} />
      <CompanyEvidenceRefSection refs={company.evidence_refs} />
      <CompanyListSection title="验证重点" items={company.verification_focus} />
      <CompanyCardSection title="待补证据">
        <ul>
          {company.next_checks.slice(0, 3).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </CompanyCardSection>
      <CompanyCardSection title="财务验证">
        {financialChecks.length ? (
          <ul>
            {financialChecks.map((item) => (
              <li key={item.node_id}>{item.watch}</li>
            ))}
          </ul>
        ) : (
          <p>先确认收入占比、订单和毛利变化。</p>
        )}
      </CompanyCardSection>
      <CompanyListSection title="主要风险" items={company.risks} />
    </article>
  );
}

function CompanyEvidenceRefSection({ refs }: { refs?: IndustryChainCompany["evidence_refs"] }) {
  if (!refs?.length) {
    return null;
  }

  return (
    <CompanyCardSection title="证据来源">
      <div className="industry-chain-company-evidence-refs">
        {refs.map((source) => (
          <div className="industry-chain-company-evidence-ref" key={`${source.publisher}-${source.title}`}>
            <div>
              {source.evidence_grade && <span>{source.evidence_grade}</span>}
              {source.url ? (
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.title}
                </a>
              ) : (
                <strong>{source.title}</strong>
              )}
            </div>
            <small>
              {source.publisher}
              {source.date ? ` · ${source.date}` : ""}
            </small>
            <p>{source.usage}</p>
          </div>
        ))}
      </div>
    </CompanyCardSection>
  );
}

function AttentionBadge({ company }: { company: IndustryChainCompany }) {
  if (!company.attention_label) {
    return null;
  }
  return (
    <span className={`industry-chain-attention-badge ${company.attention_level ?? "candidate"}`}>
      {company.attention_label}
    </span>
  );
}

function CompanyCardSection({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="industry-chain-company-card-section">
      <span>{title}</span>
      {children}
    </div>
  );
}

function CompanyListSection({ items, title }: { items?: string[]; title: string }) {
  if (!items?.length) {
    return null;
  }

  return (
    <CompanyCardSection title={title}>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </CompanyCardSection>
  );
}

export function CatalystPanel({ data }: { data: IndustryChainData }) {
  const catalysts = data.catalysts ?? [];
  if (!catalysts.length) {
    return null;
  }

  return (
    <section className="industry-chain-catalyst-panel">
      <div className="industry-chain-section-head">
        <div>
          <span className="eyebrow">市场催化</span>
          <h2>产业逻辑怎么传到市场关注</h2>
        </div>
        <Activity size={16} />
      </div>
      <div className="industry-chain-catalyst-grid">
        {catalysts.map((item) => (
          <article className="industry-chain-catalyst-item" key={`${item.horizon}-${item.title}`}>
            <span>{item.horizon}</span>
            <strong>{item.title}</strong>
            <p>{item.why}</p>
            <dl>
              <div>
                <dt>跟踪</dt>
                <dd>{item.watch}</dd>
              </div>
              {item.risk && (
                <div>
                  <dt>风险</dt>
                  <dd>{item.risk}</dd>
                </div>
              )}
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}

export function InvestorChecklistPanel({ data }: { data: IndustryChainData }) {
  const financialTranslations = data.financial_translations ?? [];
  const commonMisreads = data.common_misreads ?? [];
  if (!financialTranslations.length && !commonMisreads.length) {
    return null;
  }

  return (
    <section className="industry-chain-investor-grid">
      {financialTranslations.length > 0 && (
        <div className="industry-chain-financial-panel">
          <div className="industry-chain-section-head">
            <div>
              <span className="eyebrow">财务转译</span>
              <h2>逻辑成立，财报先看哪里</h2>
            </div>
            <Target size={16} />
          </div>
          <div className="industry-chain-financial-list">
            {financialTranslations.slice(0, 6).map((item) => (
              <div className="industry-chain-financial-item" key={item.node_id}>
                <strong>{item.title}</strong>
                <p>{item.watch}</p>
                <span>{item.source_hint}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {commonMisreads.length > 0 && (
        <div className="industry-chain-misread-panel">
          <div className="industry-chain-section-head">
            <div>
              <span className="eyebrow">误区提醒</span>
              <h2>这些不能直接当受益证据</h2>
            </div>
            <AlertTriangle size={16} />
          </div>
          <div className="industry-chain-misread-list">
            {commonMisreads.map((item) => (
              <div className="industry-chain-misread-item" key={item.title}>
                <strong>{item.title}</strong>
                <p>{item.correction}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export function TrackingPanel({ data }: { data: IndustryChainData }) {
  return (
    <section className="industry-chain-tracking-grid">
      <div className="industry-chain-tracking-panel">
        <div className="industry-chain-section-head">
          <div>
            <span className="eyebrow">跟踪指标</span>
            <h2>后续看什么</h2>
          </div>
          <Activity size={16} />
        </div>
        <div className="industry-chain-metric-list">
          {data.tracking_metrics.map((metric) => (
            <div className="industry-chain-tracking-item" key={metric.name}>
              <strong>{metric.name}</strong>
              <p>{metric.why}</p>
              <span>{metric.source_hint}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="industry-chain-source-panel">
        <div className="industry-chain-section-head">
          <div>
            <span className="eyebrow">证据来源</span>
            <h2>资料分层</h2>
          </div>
          <BookOpen size={16} />
        </div>
        <div className="industry-chain-source-list">
          {data.sources.map((source) => (
            <div className="industry-chain-source-item" key={`${source.publisher}-${source.title}`}>
              <strong>{source.publisher}</strong>
              <p>{source.title}</p>
              <span>{source.usage}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function firstStepId(data?: IndustryChainData | null): string {
  return data?.learning_steps?.[0]?.id ?? "";
}

export function preferredNodeId(data?: IndustryChainData | null): string {
  const firstStepNodeId = data?.learning_steps?.[0]?.node_ids[0];
  return firstStepNodeId ?? data?.nodes[0]?.id ?? "";
}

export function stepForNode(data: IndustryChainData | null | undefined, nodeId: string): IndustryChainLearningStep | null {
  return data?.learning_steps?.find((step) => step.node_ids.includes(nodeId)) ?? null;
}

export function relatedNodeEdges(edges: IndustryChainEdge[], nodeId?: string): IndustryChainEdge[] {
  if (!nodeId) {
    return [];
  }
  return edges.filter((edge) => edge.source === nodeId || edge.target === nodeId);
}

export function relatedNodeCompanies(companies: IndustryChainCompany[], nodeId?: string): IndustryChainCompany[] {
  if (!nodeId) {
    return [];
  }
  return companies.filter((company) => company.nodes.includes(nodeId));
}

function MetricTile({ icon, label, value }: { icon: ReactNode; label: string; value: number | string }) {
  return (
    <div className="industry-chain-metric-tile">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EvidenceBadge({ status }: { status: IndustryChainEvidenceStatus }) {
  return <span className={`industry-chain-evidence-badge ${status}`}>{evidenceStatusLabel(status)}</span>;
}

function layerLabel(layer: string): string {
  const labels: Record<string, string> = {
    upstream: "上游",
    midstream: "中游",
    downstream: "下游",
    component: "部件",
    equipment: "设备",
    material: "材料",
    service: "服务",
  };
  return labels[layer] ?? layer;
}

function groupLabel(group: string): string {
  const labels: Record<string, string> = {
    demand: "需求",
    scenario: "场景",
    system: "系统",
    core_component: "核心部件",
    core_equipment: "核心设备",
    reliability: "可靠性",
    component: "部件",
    material: "材料",
  };
  return labels[group] ?? group;
}

function evidenceStatusLabel(status: IndustryChainEvidenceStatus): string {
  switch (status) {
    case "supported":
      return "强支持";
    case "weakly_supported":
      return "弱支持";
    case "candidate":
      return "待验证";
    case "unsupported":
      return "证据不足";
    default:
      return status;
  }
}
