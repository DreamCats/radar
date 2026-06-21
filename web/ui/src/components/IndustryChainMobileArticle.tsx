import { MarkdownContent } from "./MarkdownContent";
import type {
  IndustryChainCompany,
  IndustryChainConceptDiagram,
  IndustryChainData,
  IndustryChainDetail,
  IndustryChainEdge,
  IndustryChainEvidenceStatus,
  IndustryChainLearningStep,
  IndustryChainNode,
} from "../types";

export function IndustryChainMobileArticle({ detail }: { detail: IndustryChainDetail }) {
  const data = detail.data;
  const quickRead = data.quick_read;
  const steps = data.learning_steps ?? [];

  return (
    <article className="industry-chain-mobile-article">
      <nav className="industry-chain-mobile-article-nav" aria-label="产业链长文目录">
        <a href="#industry-chain-mobile-overview">速读</a>
        <a href="#industry-chain-mobile-path">路径</a>
        <a href="#industry-chain-mobile-terms">术语</a>
        <a href="#industry-chain-mobile-market">市场</a>
        <a href="#industry-chain-mobile-tracking">跟踪</a>
      </nav>

      <section className="industry-chain-mobile-article-section" id="industry-chain-mobile-overview">
        <span className="eyebrow">3 分钟看懂</span>
        <h2>{quickRead?.headline ?? data.title}</h2>
        <p className="industry-chain-mobile-article-lead">{quickRead?.summary ?? data.summary}</p>
        {quickRead?.logic_chain?.length ? (
          <ol className="industry-chain-mobile-logic-list">
            {quickRead.logic_chain.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        ) : null}
        {quickRead?.takeaways?.length ? (
          <div className="industry-chain-mobile-takeaways">
            {quickRead.takeaways.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
        ) : null}
      </section>

      <EvidencePolicySection data={data} />

      {steps.length ? (
        <section className="industry-chain-mobile-article-section" id="industry-chain-mobile-path">
          <span className="eyebrow">认知路径</span>
          <h2>按顺序读，不靠点图谱理解</h2>
          <div className="industry-chain-mobile-step-list">
            {steps.map((step, index) => (
              <StepArticle data={data} index={index} key={step.id} step={step} />
            ))}
          </div>
        </section>
      ) : null}

      <ConceptArticleSection data={data} />
      <MarketArticleSection data={data} />
      <TrackingArticleSection data={data} />

      <details className="industry-chain-mobile-manuscript">
        <summary>
          <span>完整学习稿</span>
          <em>原稿补充</em>
        </summary>
        <MarkdownContent content={detail.content_markdown} />
      </details>
    </article>
  );
}

function EvidencePolicySection({ data }: { data: IndustryChainData }) {
  const labels = data.evidence_policy?.labels ?? [];
  if (!labels.length) {
    return null;
  }

  return (
    <section className="industry-chain-mobile-article-section">
      <span className="eyebrow">证据口径</span>
      <h2>先分清确定性</h2>
      <div className="industry-chain-mobile-evidence-list">
        {labels.map((item) => (
          <div className="industry-chain-mobile-evidence-item" key={item.status}>
            <EvidencePill status={item.status} />
            <strong>{item.meaning}</strong>
            <p>{item.evidence_needed}</p>
          </div>
        ))}
      </div>
      {data.evidence_policy?.upgrade_rule ? (
        <p className="industry-chain-mobile-note">{data.evidence_policy.upgrade_rule}</p>
      ) : null}
    </section>
  );
}

function StepArticle({ data, index, step }: { data: IndustryChainData; index: number; step: IndustryChainLearningStep }) {
  const nodes = nodesForStep(data, step);
  const edges = edgesForNodes(data.edges, step.node_ids);
  const companies = companiesForNodes(data.companies, step.node_ids);

  return (
    <section className="industry-chain-mobile-step">
      <div className="industry-chain-mobile-step-head">
        <b>{index + 1}</b>
        <div>
          <span>{step.title}</span>
          <h3>{step.question}</h3>
        </div>
      </div>
      <p className="industry-chain-mobile-step-answer">{step.answer}</p>
      {step.subtitle ? <p className="industry-chain-mobile-step-subtitle">{step.subtitle}</p> : null}

      {nodes.map((node) => (
        <NodeArticle key={node.id} node={node} />
      ))}

      {edges.length ? (
        <div className="industry-chain-mobile-relation-block">
          <strong>这一段的因果关系</strong>
          {edges.map((edge) => (
            <p key={`${edge.source}-${edge.target}`}>
              {nodeLabel(data.nodes, edge.source)} <span>→</span> {nodeLabel(data.nodes, edge.target)}：{edge.description}
            </p>
          ))}
        </div>
      ) : null}

      {companies.length ? (
        <div className="industry-chain-mobile-company-block">
          <strong>相关 A 股映射</strong>
          {companies.map((company) => (
            <CompanyArticleCard company={company} data={data} key={company.ts_code} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function NodeArticle({ node }: { node: IndustryChainNode }) {
  return (
    <section className="industry-chain-mobile-node-article">
      <div className="industry-chain-mobile-node-head">
        <h4>{node.label}</h4>
        <EvidencePill status={node.evidence_status} />
      </div>
      <p>{node.beginner_explanation}</p>
      {node.teach ? (
        <div className="industry-chain-mobile-teach-grid">
          <ArticleFact title="它是什么" value={node.teach.what} />
          <ArticleFact title="为什么重要" value={node.teach.why_matters} />
          <ArticleFact title="怎么受益" value={node.teach.benefit_logic} />
          <ArticleFact title="常见误区" value={node.teach.common_misread} />
          {node.teach.watch.length ? (
            <div className="industry-chain-mobile-watch-tags">
              <span>重点看</span>
              <div>
                {node.teach.watch.map((item) => (
                  <em key={item}>{item}</em>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      <p className="industry-chain-mobile-node-score">产业链关键度 {node.bottleneck_strength}/5</p>
    </section>
  );
}

function CompanyArticleCard({ company, data }: { company: IndustryChainCompany; data: IndustryChainData }) {
  const nodeNames = company.nodes.map((nodeId) => nodeLabel(data.nodes, nodeId)).filter(Boolean);
  const evidenceCount = (company.evidence_basis?.length ?? 0) + (company.evidence_refs?.length ?? 0);
  const riskCount = (company.verification_focus?.length ?? 0) + (company.next_checks?.length ?? 0) + (company.risks?.length ?? 0);

  return (
    <section className="industry-chain-mobile-company-card">
      <div className="industry-chain-mobile-company-head">
        <div>
          <strong>{company.name}</strong>
          <span>{company.ts_code}</span>
        </div>
        <EvidencePill status={company.evidence_status} />
      </div>
      {company.attention_label ? <em className="industry-chain-mobile-attention">{company.attention_label}</em> : null}
      <p>{company.role}</p>
      {company.why_watch ? <p>{company.why_watch}</p> : null}
      {nodeNames.length ? (
        <div className="industry-chain-mobile-node-tags">
          {nodeNames.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      ) : null}
      <p className="industry-chain-mobile-current-view">{company.current_view}</p>
      <details>
        <summary>
          <span>证据和验证</span>
          <em>{evidenceCount + riskCount} 项</em>
        </summary>
        <CompanyList title="证据依据" items={company.evidence_basis} />
        <CompanyEvidenceRefs refs={company.evidence_refs} />
        <CompanyList title="验证重点" items={company.verification_focus} />
        <CompanyList title="待补证据" items={company.next_checks?.slice(0, 3)} />
        <CompanyList title="主要风险" items={company.risks} />
      </details>
    </section>
  );
}

function ConceptArticleSection({ data }: { data: IndustryChainData }) {
  const diagrams = data.concept_diagrams ?? [];
  if (!diagrams.length) {
    return null;
  }

  return (
    <section className="industry-chain-mobile-article-section" id="industry-chain-mobile-terms">
      <span className="eyebrow">术语图解</span>
      <h2>把专业词变成阅读段落</h2>
      {diagrams.map((diagram) => (
        <ConceptArticleCard diagram={diagram} key={diagram.id} />
      ))}
    </section>
  );
}

function ConceptArticleCard({ diagram }: { diagram: IndustryChainConceptDiagram }) {
  return (
    <section className="industry-chain-mobile-concept-card">
      <strong>{diagram.title}</strong>
      <p>{diagram.subtitle}</p>
      <ol>
        {diagram.parts.map((part) => (
          <li key={part.label}>
            <span>{part.role}</span>
            <b>{part.label}</b>
            <p>{part.description}</p>
          </li>
        ))}
      </ol>
      <p className="industry-chain-mobile-note">{diagram.takeaway}</p>
    </section>
  );
}

function MarketArticleSection({ data }: { data: IndustryChainData }) {
  const catalysts = data.catalysts ?? [];
  const financials = data.financial_translations ?? [];
  const misreads = data.common_misreads ?? [];
  if (!catalysts.length && !financials.length && !misreads.length) {
    return null;
  }

  return (
    <section className="industry-chain-mobile-article-section" id="industry-chain-mobile-market">
      <span className="eyebrow">市场转译</span>
      <h2>产业逻辑怎么落到投资观察</h2>
      {catalysts.length ? (
        <div className="industry-chain-mobile-card-list">
          {catalysts.map((item) => (
            <section className="industry-chain-mobile-market-card" key={`${item.horizon}-${item.title}`}>
              <span>{item.horizon}</span>
              <strong>{item.title}</strong>
              <p>{item.why}</p>
              <small>跟踪：{item.watch}</small>
              {item.risk ? <small>风险：{item.risk}</small> : null}
            </section>
          ))}
        </div>
      ) : null}
      <FoldList title="财务验证" items={financials.map((item) => `${item.title}：${item.watch}`)} />
      <FoldList title="常见误区" items={misreads.map((item) => `${item.title}：${item.correction}`)} />
    </section>
  );
}

function TrackingArticleSection({ data }: { data: IndustryChainData }) {
  return (
    <section className="industry-chain-mobile-article-section" id="industry-chain-mobile-tracking">
      <span className="eyebrow">跟踪资料</span>
      <h2>后续看什么</h2>
      <div className="industry-chain-mobile-card-list">
        {data.tracking_metrics.map((metric) => (
          <section className="industry-chain-mobile-tracking-card" key={metric.name}>
            <strong>{metric.name}</strong>
            <p>{metric.why}</p>
            <small>{metric.source_hint}</small>
          </section>
        ))}
      </div>
      <details className="industry-chain-mobile-source-fold">
        <summary>
          <span>资料来源</span>
          <em>{data.sources.length} 条</em>
        </summary>
        <div>
          {data.sources.map((source) => (
            <section className="industry-chain-mobile-source-card" key={`${source.publisher}-${source.title}`}>
              <strong>{source.publisher}</strong>
              <p>{source.title}</p>
              <small>{source.usage}</small>
            </section>
          ))}
        </div>
      </details>
    </section>
  );
}

function ArticleFact({ title, value }: { title: string; value: string }) {
  return (
    <div className="industry-chain-mobile-fact">
      <span>{title}</span>
      <p>{value}</p>
    </div>
  );
}

function FoldList({ items, title }: { items: string[]; title: string }) {
  if (!items.length) {
    return null;
  }

  return (
    <details className="industry-chain-mobile-source-fold">
      <summary>
        <span>{title}</span>
        <em>{items.length} 项</em>
      </summary>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </details>
  );
}

function CompanyList({ items, title }: { items?: string[]; title: string }) {
  if (!items?.length) {
    return null;
  }

  return (
    <div className="industry-chain-mobile-company-list">
      <span>{title}</span>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function CompanyEvidenceRefs({ refs }: { refs?: IndustryChainCompany["evidence_refs"] }) {
  if (!refs?.length) {
    return null;
  }

  return (
    <div className="industry-chain-mobile-company-list">
      <span>证据来源</span>
      {refs.map((source) => (
        <p key={`${source.publisher}-${source.title}`}>
          {source.evidence_grade ? `${source.evidence_grade} · ` : ""}
          {source.publisher}：{source.title}
          {source.usage ? `。${source.usage}` : ""}
        </p>
      ))}
    </div>
  );
}

function EvidencePill({ status }: { status: IndustryChainEvidenceStatus }) {
  return <span className={`industry-chain-mobile-evidence-pill ${status}`}>{evidenceStatusLabel(status)}</span>;
}

function nodesForStep(data: IndustryChainData, step: IndustryChainLearningStep): IndustryChainNode[] {
  const nodesById = new Map(data.nodes.map((node) => [node.id, node]));
  return step.node_ids.map((nodeId) => nodesById.get(nodeId)).filter((node): node is IndustryChainNode => Boolean(node));
}

function edgesForNodes(edges: IndustryChainEdge[], nodeIds: string[]): IndustryChainEdge[] {
  const nodeSet = new Set(nodeIds);
  return edges.filter((edge) => nodeSet.has(edge.source) || nodeSet.has(edge.target));
}

function companiesForNodes(companies: IndustryChainCompany[], nodeIds: string[]): IndustryChainCompany[] {
  const nodeSet = new Set(nodeIds);
  return companies.filter((company) => company.nodes.some((nodeId) => nodeSet.has(nodeId)));
}

function nodeLabel(nodes: IndustryChainNode[], nodeId: string): string {
  return nodes.find((node) => node.id === nodeId)?.label ?? nodeId;
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
