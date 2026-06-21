import { useEffect, useRef, useState } from "react";

import {
  Background,
  Controls,
  Position,
  ReactFlow,
  type Edge as FlowEdge,
  type Node as FlowNode,
  type ReactFlowInstance,
} from "@xyflow/react";

import type {
  IndustryChainData,
  IndustryChainEdge,
  IndustryChainLearningStep,
  IndustryChainNode,
} from "../types";
import { buildGraphEdges, FlowNodeLabel, isGraphMetaNode, type GraphColumn } from "./IndustryChainGraphShared";
import { buildKnowledgeGraphEdges, buildKnowledgeGraphNodes } from "./IndustryChainKnowledgeGraph";

const COLUMN_X = 190;
const MAIN_Y = 74;
const BRANCH_Y = 104;
const COLUMN_LABEL_Y = -72;

type GraphViewMode = "map" | "path";

const LEGACY_GRAPH_COLUMNS: GraphColumn[] = [
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
  const [viewMode, setViewMode] = useState<GraphViewMode>("map");
  const columns = graphColumnsForData(data);
  const nodeLayouts = buildNodeLayouts(data, columns);
  const activeNodeIds = new Set(activeStep?.node_ids ?? []);
  const relatedNodeIds = new Set(relatedEdges.flatMap((edge) => [edge.source, edge.target]));
  const nodes =
    viewMode === "map"
      ? buildKnowledgeGraphNodes(data, selectedNode?.id, activeNodeIds, relatedNodeIds, columns)
      : buildFlowNodes(data, selectedNode?.id, activeNodeIds, relatedNodeIds, columns, nodeLayouts);
  const edges =
    viewMode === "map"
      ? buildKnowledgeGraphEdges(data, selectedNode?.id, activeNodeIds, relatedEdges, columns)
      : buildGraphEdges(data, selectedNode?.id, activeNodeIds, relatedEdges);
  const nodesById = new Map(data.nodes.map((node) => [node.id, node]));

  return (
    <section className="industry-chain-graph-panel">
      <div className="industry-chain-section-head">
        <div>
          <span className="eyebrow">全局知识图谱</span>
          <h2>{graphTitle(viewMode, data.title, activeStep)}</h2>
        </div>
        <div className="industry-chain-graph-actions industry-chain-graph-desktop-actions">
          <GraphModeSwitch viewMode={viewMode} onSetViewMode={setViewMode} />
          <span className="industry-chain-status-pill">{viewMode === "map" ? "知识图谱" : "路径分镜"}</span>
        </div>
      </div>
      <MobileChainRail columns={columns} data={data} selectedNodeId={selectedNode?.id} onSelectNode={onSelectNode} />
      <MobileSelectedNodeSummary node={selectedNode} relatedEdges={relatedEdges} />
      <div className="industry-chain-flow-desktop">
        <FlowCanvas edges={edges} graphKey={data.chain_id} mode={viewMode} nodes={nodes} onSelectNode={onSelectNode} />
      </div>
      <details className="industry-chain-flow-mobile-details">
        <summary>展开完整图谱</summary>
        <div className="industry-chain-flow-mobile-controls">
          <GraphModeSwitch viewMode={viewMode} onSetViewMode={setViewMode} />
        </div>
        <FlowCanvas edges={edges} graphKey={data.chain_id} mode={viewMode} nodes={nodes} onSelectNode={onSelectNode} />
      </details>
      <CausalRelationStrip edges={relatedEdges} nodesById={nodesById} onSelectNode={onSelectNode} />
    </section>
  );
}

function GraphModeSwitch({
  viewMode,
  onSetViewMode,
}: {
  viewMode: GraphViewMode;
  onSetViewMode: (mode: GraphViewMode) => void;
}) {
  return (
    <div className="industry-chain-segmented" role="tablist" aria-label="图谱视图">
      <button
        className={viewMode === "map" ? "active" : ""}
        type="button"
        role="tab"
        aria-selected={viewMode === "map"}
        onClick={() => onSetViewMode("map")}
      >
        全量图谱
      </button>
      <button
        className={viewMode === "path" ? "active" : ""}
        type="button"
        role="tab"
        aria-selected={viewMode === "path"}
        onClick={() => onSetViewMode("path")}
      >
        学习路径
      </button>
    </div>
  );
}

function FlowCanvas({
  edges,
  graphKey,
  mode,
  nodes,
  onSelectNode,
}: {
  edges: FlowEdge[];
  graphKey: string;
  mode: GraphViewMode;
  nodes: FlowNode[];
  onSelectNode: (nodeId: string) => void;
}) {
  const flowRef = useRef<ReactFlowInstance | null>(null);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      void flowRef.current?.fitView({ padding: 0.12, duration: 220 });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [graphKey, mode]);

  return (
    <div className={`industry-chain-flow-canvas ${mode === "map" ? "knowledge-map" : "path-map"}`}>
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
        onInit={(instance) => {
          flowRef.current = instance;
        }}
        onNodeClick={(_, node) => {
          if (!isGraphMetaNode(node.id)) {
            onSelectNode(node.id);
          }
        }}
      >
        <Background color="rgba(138, 143, 152, 0.16)" gap={20} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}

function graphTitle(mode: GraphViewMode, title: string, activeStep: IndustryChainLearningStep | null): string {
  if (mode === "map") {
    return `${title} 的核心关系地图`;
  }
  return activeStep ? `${activeStep.title}：${activeStep.question}` : "从外部需求到内部卡点";
}

function MobileChainRail({
  columns,
  data,
  selectedNodeId,
  onSelectNode,
}: {
  columns: GraphColumn[];
  data: IndustryChainData;
  selectedNodeId?: string;
  onSelectNode: (nodeId: string) => void;
}) {
  const nodesById = new Map(data.nodes.map((node) => [node.id, node]));
  return (
    <div className="industry-chain-mobile-rail" aria-label="移动端简化产业链">
      {columns.map((column, index) => {
        const columnNodes = column.nodeIds
          .map((nodeId) => nodesById.get(nodeId))
          .filter((node): node is IndustryChainNode => Boolean(node));
        if (!columnNodes.length) {
          return null;
        }
        return (
          <article className="industry-chain-mobile-rail-group" key={column.key}>
            <div className="industry-chain-mobile-rail-head">
              <b>{index + 1}</b>
              <span>{column.label}</span>
              <em>{column.description}</em>
            </div>
            <div className="industry-chain-mobile-rail-nodes">
              {columnNodes.map((node) => (
                <button
                  className={node.id === selectedNodeId ? "active" : ""}
                  type="button"
                  key={node.id}
                  onClick={() => onSelectNode(node.id)}
                >
                  {node.label}
                </button>
              ))}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function MobileSelectedNodeSummary({
  node,
  relatedEdges,
}: {
  node: IndustryChainNode | null;
  relatedEdges: IndustryChainEdge[];
}) {
  if (!node) {
    return null;
  }

  return (
    <div className="industry-chain-mobile-node-summary">
      <span>当前节点</span>
      <strong>{node.label}</strong>
      <p>{node.beginner_explanation}</p>
      <em>
        关键度 {node.bottleneck_strength}/5
        {relatedEdges.length ? ` · ${relatedEdges.length} 条相关关系` : ""}
      </em>
    </div>
  );
}

function buildFlowNodes(
  data: IndustryChainData,
  selectedNodeId: string | undefined,
  activeNodeIds: Set<string>,
  relatedNodeIds: Set<string>,
  columns: GraphColumn[],
  nodeLayouts: Map<string, { column: number; row: number }>,
): FlowNode[] {
  const columnHeaderNodes = columns.map((column, index) => ({
    id: `column-${column.key}`,
    position: { x: index * COLUMN_X, y: COLUMN_LABEL_Y },
    data: { label: <ColumnLabel description={column.description} label={column.label} /> },
    className: "industry-chain-flow-column-label",
    draggable: false,
    selectable: false,
  }));
  const chainNodes = data.nodes.map((node) => {
    const layout = nodeLayouts.get(node.id) ?? { column: 0, row: 0 };
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

function graphColumnsForData(data: IndustryChainData): GraphColumn[] {
  if (!data.flow_columns?.length) {
    return LEGACY_GRAPH_COLUMNS;
  }
  return data.flow_columns.map((column) => ({
    key: column.key,
    label: column.label,
    description: column.description,
    nodeIds: column.node_ids,
  }));
}

function buildNodeLayouts(data: IndustryChainData, columns: GraphColumn[]): Map<string, { column: number; row: number }> {
  const layouts = new Map<string, { column: number; row: number }>();
  const nextRowByColumn = new Map<number, number>();

  if (!data.flow_columns?.length) {
    Object.entries(NODE_LAYOUT).forEach(([nodeId, layout]) => {
      layouts.set(nodeId, layout);
      nextRowByColumn.set(layout.column, Math.max(nextRowByColumn.get(layout.column) ?? 0, layout.row + 1));
    });
    data.nodes.forEach((node) => {
      if (layouts.has(node.id)) {
        return;
      }
      const column = Math.max(
        0,
        columns.findIndex((item) => item.nodeIds.includes(node.id)),
      );
      const row = nextRowByColumn.get(column) ?? 0;
      layouts.set(node.id, { column, row });
      nextRowByColumn.set(column, row + 1);
    });
    return layouts;
  }

  columns.forEach((column, columnIndex) => {
    column.nodeIds.forEach((nodeId, rowIndex) => {
      layouts.set(nodeId, { column: columnIndex, row: rowIndex });
      nextRowByColumn.set(columnIndex, Math.max(nextRowByColumn.get(columnIndex) ?? 0, rowIndex + 1));
    });
  });

  data.nodes.forEach((node) => {
    if (layouts.has(node.id)) {
      return;
    }
    const column = Math.max(
      0,
      columns.findIndex((item) => item.nodeIds.includes(node.id)),
    );
    const row = nextRowByColumn.get(column) ?? 0;
    layouts.set(node.id, { column, row });
    nextRowByColumn.set(column, row + 1);
  });

  return layouts;
}

function ColumnLabel({ description, label }: { description: string; label: string }) {
  return (
    <div className="industry-chain-flow-column-label-inner">
      <span>{label}</span>
      <em>{description}</em>
    </div>
  );
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
