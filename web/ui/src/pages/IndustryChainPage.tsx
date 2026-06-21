import { useEffect, useMemo, useState } from "react";

import { fetchIndustryChainDetail, fetchIndustryChains } from "../api/radarApi";
import { IndustryChainGraph } from "../components/IndustryChainFlowGraph";
import { IndustryChainMobileArticle } from "../components/IndustryChainMobileArticle";
import {
  CatalystPanel,
  CompanyRolePanel,
  ConceptDiagramPanel,
  EvidenceGuidePanel,
  IndustryChainHeader,
  InvestorChecklistPanel,
  LearningPathPanel,
  NodeDetailPanel,
  QuickReadPanel,
  TrackingPanel,
  firstStepId,
  preferredNodeId,
  relatedNodeCompanies,
  relatedNodeEdges,
  stepForNode,
} from "../components/IndustryChainPanels";
import { MarkdownContent } from "../components/MarkdownContent";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import type { IndustryChainCompany, IndustryChainDetail, IndustryChainIndexItem } from "../types";

export function IndustryChainPage() {
  const [chains, setChains] = useState<IndustryChainIndexItem[]>([]);
  const [selectedChainId, setSelectedChainId] = useState("");
  const [detail, setDetail] = useState<IndustryChainDetail | null>(null);
  const [activeStepId, setActiveStepId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [companyTier, setCompanyTier] = useState("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(chainId = selectedChainId) {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchIndustryChains();
      const nextChains = [...list.items].sort((a, b) => a.sort_order - b.sort_order);
      const nextChainId = chainId || nextChains[0]?.chain_id || "";
      const nextDetail = nextChainId ? await fetchIndustryChainDetail(nextChainId) : null;
      setChains(nextChains);
      setSelectedChainId(nextChainId);
      setDetail(nextDetail);
      setActiveStepId(firstStepId(nextDetail?.data));
      setSelectedNodeId(preferredNodeId(nextDetail?.data));
      setCompanyTier("all");
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载产业链失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const selectedNode = useMemo(
    () => detail?.data.nodes.find((node) => node.id === selectedNodeId) ?? detail?.data.nodes[0] ?? null,
    [detail, selectedNodeId],
  );
  const relatedEdges = useMemo(
    () => relatedNodeEdges(detail?.data.edges ?? [], selectedNode?.id),
    [detail, selectedNode?.id],
  );
  const relatedCompanies = useMemo(
    () => relatedNodeCompanies(detail?.data.companies ?? [], selectedNode?.id),
    [detail, selectedNode?.id],
  );
  const filteredCompanies = useMemo(() => {
    const companies = detail?.data.companies ?? [];
    const sortedCompanies = [...companies].sort((a, b) => companyAttentionRank(a) - companyAttentionRank(b));
    if (companyTier === "all") {
      return sortedCompanies;
    }
    if (companyTier === "leader") {
      return sortedCompanies.filter((company) => company.attention_level === "leader");
    }
    return sortedCompanies.filter((company) => company.tier === companyTier);
  }, [companyTier, detail]);

  const initialLoading = loading && !detail;
  const activeStep =
    detail?.data.learning_steps?.find((step) => step.id === activeStepId) ?? detail?.data.learning_steps?.[0] ?? null;

  function selectNode(nodeId: string) {
    setSelectedNodeId(nodeId);
    const nextStep = stepForNode(detail?.data, nodeId);
    if (nextStep) {
      setActiveStepId(nextStep.id);
    }
  }

  function selectStep(stepId: string) {
    const step = detail?.data.learning_steps?.find((item) => item.id === stepId);
    setActiveStepId(stepId);
    if (step?.node_ids[0]) {
      setSelectedNodeId(step.node_ids[0]);
    }
  }

  return (
    <section className="industry-chain-page">
      <div className="industry-chain-actions">
        <p>{pageHeaderText(initialLoading, detail)}</p>
        <label className="industry-chain-picker">
          <span>产业链</span>
          <select
            value={selectedChainId}
            disabled={loading || chains.length === 0}
            aria-label="选择产业链"
            onChange={(event) => void refresh(event.target.value)}
          >
            {chains.map((chain) => (
              <option value={chain.chain_id} key={chain.chain_id}>
                {chain.title}
              </option>
            ))}
          </select>
        </label>
        {loading && !initialLoading && <PageRefreshProgress label="正在刷新产业链" />}
      </div>

      <main className="industry-chain-main">
        {initialLoading ? (
          <PageLoadingState label="正在加载产业链内容" variant="strategy" />
        ) : error ? (
          <p className="industry-chain-error">{error}</p>
        ) : detail ? (
          <>
            <IndustryChainHeader detail={detail} />
            <IndustryChainMobileArticle detail={detail} />
            <div className="industry-chain-desktop-workspace">
              <div className="industry-chain-anchor" id="industry-chain-overview">
                <QuickReadPanel data={detail.data} />
                <EvidenceGuidePanel data={detail.data} />
              </div>
              <div className="industry-chain-anchor" id="industry-chain-path">
                <LearningPathPanel activeStepId={activeStepId} data={detail.data} onSelectStep={selectStep} />
              </div>
              <section className="industry-chain-focus-grid industry-chain-anchor" id="industry-chain-graph">
                <IndustryChainGraph
                  activeStep={activeStep}
                  data={detail.data}
                  relatedEdges={relatedEdges}
                  selectedNode={selectedNode}
                  onSelectNode={selectNode}
                />
                <NodeDetailPanel
                  activeStep={activeStep}
                  companies={relatedCompanies}
                  edges={relatedEdges}
                  node={selectedNode}
                />
              </section>
              <ConceptDiagramPanel data={detail.data} onSelectNode={selectNode} />
              <div className="industry-chain-anchor" id="industry-chain-companies">
                <CompanyRolePanel
                  companies={filteredCompanies}
                  data={detail.data}
                  selectedNode={selectedNode}
                  tier={companyTier}
                  onSelectNode={selectNode}
                  onSetTier={setCompanyTier}
                />
              </div>
              <CatalystPanel data={detail.data} />
              <InvestorChecklistPanel data={detail.data} />
              <div className="industry-chain-anchor" id="industry-chain-tracking">
                <TrackingPanel data={detail.data} />
              </div>
              <details className="industry-chain-markdown-panel industry-chain-anchor" id="industry-chain-manuscript">
                <summary>
                  <span>展开完整学习稿</span>
                  <em>原稿信息量较大，默认收起</em>
                </summary>
                <MarkdownContent content={detail.content_markdown} />
              </details>
            </div>
          </>
        ) : (
          <p className="industry-chain-error">暂无产业链内容</p>
        )}
      </main>
    </section>
  );
}

function companyAttentionRank(company: IndustryChainCompany): number {
  const ranks: Record<string, number> = {
    leader: 0,
    core_candidate: 1,
    watch: 2,
    candidate: 3,
  };
  return ranks[company.attention_level ?? "candidate"] ?? 4;
}

function pageHeaderText(loading: boolean, detail: IndustryChainDetail | null): string {
  if (loading) {
    return "正在加载产业链内容";
  }
  if (!detail) {
    return "暂无产业链内容";
  }
  return `${detail.item.title} · ${detail.data.nodes.length} 个节点 · ${detail.data.companies.length} 家公司`;
}
