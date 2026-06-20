import {
  Background,
  Controls,
  MarkerType,
  Position,
  ReactFlow,
  type Edge as FlowEdge,
  type Node as FlowNode,
} from "@xyflow/react";

import type {
  IndustryChainData,
  IndustryChainEdge,
  IndustryChainLearningStep,
  IndustryChainNode,
} from "../types";

const COLUMN_X = 190;
const MAIN_Y = 74;
const BRANCH_Y = 104;
const COLUMN_LABEL_Y = -72;

const GRAPH_COLUMNS = [
  { key: "demand", label: "需求牵引", description: "AI 为什么拉动算力", nodeIds: ["demand-ai-compute"] },
  { key: "server", label: "服务器功耗", description: "功耗和热密度上升", nodeIds: ["ai-server"] },
  { key: "scenario", label: "场景压力", description: "风冷开始不够用", nodeIds: ["high-density-rack"] },
  { key: "system", label: "系统方案", description: "液冷成为完整方案", nodeIds: ["liquid-system"] },
  {
    key: "core",
    label: "核心部件",
    description: "冷板、接头、CDU 等",
    nodeIds: ["cold-plate", "uqd", "manifold", "cdu", "monitoring"],
  },
  { key: "support", label: "二阶支撑", description: "管路、冷却液等配套", nodeIds: ["pump-valve-pipe", "coolant"] },
];

const NODE_LAYOUT: Record<string, { column: number; row: number }> = {
  "demand-ai-compute": { column: 0, row: 0 },
  "ai-server": { column: 1, row: 0 },
  "high-density-rack": { column: 2, row: 0 },
  "liquid-system": { column: 3, row: 0 },
  "cold-plate": { column: 4, row: 0 },
  uqd: { column: 4, row: 1 },
  manifold: { column: 4, row: 2 },
  cdu: { column: 4, row: 3 },
  monitoring: { column: 4, row: 4 },
  coolant: { column: 5, row: 2 },
  "pump-valve-pipe": { column: 5, row: 3 },
};

const NODE_BADGE_LABELS: Record<string, string> = {
  "demand-ai-compute": "驱动",
  "ai-server": "功耗",
  "high-density-rack": "压力",
  "liquid-system": "方案",
  "cold-plate": "卡点",
  uqd: "卡点",
  manifold: "卡点",
  cdu: "卡点",
  monitoring: "卡点",
  coolant: "支撑",
  "pump-valve-pipe": "支撑",
};

export function IndustryChainGraph({
  activeStep,
  data,
  relatedEdges,
  selectedNode,
  onSelectNode,
}: {
  activeStep: IndustryChainLearningStep | null;
  data: IndustryChainData;
  relatedEdges: IndustryChainEdge[];
  selectedNode: IndustryChainNode | null;
  onSelectNode: (nodeId: string) => void;
}) {
  const activeNodeIds = new Set(activeStep?.node_ids ?? []);
  const relatedNodeIds = new Set(relatedEdges.flatMap((edge) => [edge.source, edge.target]));
  const nodes = buildFlowNodes(data, selectedNode?.id, activeNodeIds, relatedNodeIds);
  const edges = buildFlowEdges(data, selectedNode?.id, activeNodeIds, relatedEdges);
  const nodesById = new Map(data.nodes.map((node) => [node.id, node]));

  return (
    <section className="industry-chain-graph-panel">
      <div className="industry-chain-section-head">
        <div>
          <span className="eyebrow">全局关系链</span>
          <h2>{activeStep ? `${activeStep.title}：${activeStep.question}` : "从外部需求到内部卡点"}</h2>
        </div>
        <span className="industry-chain-status-pill">{activeStep ? "当前分镜" : statusLabel(data.status)}</span>
      </div>
      <div className="industry-chain-flow-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          minZoom={0.42}
          maxZoom={1.45}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, node) => {
            if (!node.id.startsWith("column-")) {
              onSelectNode(node.id);
            }
          }}
        >
          <Background color="rgba(138, 143, 152, 0.16)" gap={20} />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </div>
      <CausalRelationStrip edges={relatedEdges} nodesById={nodesById} onSelectNode={onSelectNode} />
    </section>
  );
}

function buildFlowNodes(
  data: IndustryChainData,
  selectedNodeId: string | undefined,
  activeNodeIds: Set<string>,
  relatedNodeIds: Set<string>,
): FlowNode[] {
  const columnHeaderNodes = GRAPH_COLUMNS.map((column, index) => ({
    id: `column-${column.key}`,
    position: { x: index * COLUMN_X, y: COLUMN_LABEL_Y },
    data: { label: <ColumnLabel description={column.description} label={column.label} /> },
    className: "industry-chain-flow-column-label",
    draggable: false,
    selectable: false,
  }));
  const chainNodes = data.nodes.map((node) => {
    const layout = NODE_LAYOUT[node.id] ?? fallbackNodeLayout(node);
    const selected = node.id === selectedNodeId;
    const active = activeNodeIds.has(node.id);
    const related = relatedNodeIds.has(node.id);
    const dimmed = activeNodeIds.size > 0 && !active && !related && !selected;
    return {
      id: node.id,
      position: { x: layout.column * COLUMN_X, y: MAIN_Y + layout.row * BRANCH_Y },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: { label: <FlowNodeLabel node={node} /> },
      className: [
        "industry-chain-flow-node",
        node.evidence_status,
        selected ? "selected" : "",
        active ? "active-step" : "",
        related ? "related" : "",
        dimmed ? "dimmed" : "",
      ]
        .filter(Boolean)
        .join(" "),
    };
  });
  return [...columnHeaderNodes, ...chainNodes];
}

function fallbackNodeLayout(node: IndustryChainNode): { column: number; row: number } {
  const column = GRAPH_COLUMNS.findIndex((item) => item.nodeIds.includes(node.id));
  return { column: Math.max(0, column), row: 0 };
}

function ColumnLabel({ description, label }: { description: string; label: string }) {
  return (
    <div className="industry-chain-flow-column-label-inner">
      <span>{label}</span>
      <em>{description}</em>
    </div>
  );
}

function FlowNodeLabel({ node }: { node: IndustryChainNode }) {
  const badge = flowNodeBadge(node);
  return (
    <div className="industry-chain-flow-node-label">
      <span>{node.label}</span>
      <em>{node.beginner_explanation}</em>
      <b aria-label={badge.title} title={badge.title}>
        {badge.label}
      </b>
    </div>
  );
}

function flowNodeBadge(node: IndustryChainNode): { label: string; title: string } {
  const label = NODE_BADGE_LABELS[node.id] ?? fallbackBadgeLabel(node.group);
  return { label, title: `${label}节点，产业链关键度 ${node.bottleneck_strength}/5` };
}

function fallbackBadgeLabel(group: string): string {
  const labels: Record<string, string> = {
    demand: "驱动",
    scenario: "压力",
    system: "方案",
    core_component: "卡点",
    core_equipment: "卡点",
    reliability: "卡点",
    component: "支撑",
    material: "支撑",
  };
  return labels[group] ?? "节点";
}

function buildFlowEdges(
  data: IndustryChainData,
  selectedNodeId: string | undefined,
  activeNodeIds: Set<string>,
  relatedEdges: IndustryChainEdge[],
): FlowEdge[] {
  const relatedKeys = new Set(relatedEdges.map((edge) => `${edge.source}-${edge.target}`));
  return data.edges.map((edge) => {
    const related = relatedKeys.has(`${edge.source}-${edge.target}`);
    const active = activeNodeIds.has(edge.source) && activeNodeIds.has(edge.target);
    const selected = edge.source === selectedNodeId || edge.target === selectedNodeId;
    const color = edgeColor(selected || active, related);
    const primary = selected || active || related;
    return {
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      type: "straight",
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, color },
      style: { stroke: color, strokeWidth: selected || active ? 2.2 : 1.4, opacity: primary ? 1 : 0.2 },
    };
  });
}

function edgeColor(primary: boolean, related: boolean): string {
  if (primary) {
    return "rgba(130, 143, 255, 0.92)";
  }
  if (related) {
    return "rgba(138, 143, 152, 0.62)";
  }
  return "rgba(98, 102, 109, 0.32)";
}

function CausalRelationStrip({
  edges,
  nodesById,
  onSelectNode,
}: {
  edges: IndustryChainEdge[];
  nodesById: Map<string, IndustryChainNode>;
  onSelectNode: (nodeId: string) => void;
}) {
  if (!edges.length) {
    return null;
  }

  return (
    <div className="industry-chain-causal-strip" aria-label="这一步的因果关系">
      <div className="industry-chain-causal-head">
        <span>这一步的因果关系</span>
        <em>点击任意关系可跳到目标节点</em>
      </div>
      <div className="industry-chain-causal-grid">
        {edges.map((edge) => (
          <button
            className="industry-chain-causal-chip"
            type="button"
            key={`${edge.source}-${edge.target}`}
            onClick={() => onSelectNode(edge.target)}
          >
            <span>
              {nodesById.get(edge.source)?.label ?? edge.source}
              <i>→</i>
              {nodesById.get(edge.target)?.label ?? edge.target}
            </span>
            <strong>{edge.label}</strong>
            <em>{edge.description}</em>
          </button>
        ))}
      </div>
    </div>
  );
}

function statusLabel(status: string): string {
  return status === "draft" ? "草案" : status === "active" ? "已发布" : status;
}
