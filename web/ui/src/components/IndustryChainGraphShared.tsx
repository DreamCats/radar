import { MarkerType, type Edge as FlowEdge } from "@xyflow/react";

import type { IndustryChainData, IndustryChainEdge, IndustryChainFlowColumn, IndustryChainNode } from "../types";

export const MAP_ROOT_ID = "map-root";

export type GraphColumn = Omit<IndustryChainFlowColumn, "node_ids"> & {
  nodeIds: string[];
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

export function FlowNodeLabel({ node }: { node: IndustryChainNode }) {
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

export function buildGraphEdges(
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

export function mapGroupId(key: string): string {
  return `map-group-${key}`;
}

export function isGraphMetaNode(nodeId: string): boolean {
  return nodeId === MAP_ROOT_ID || nodeId.startsWith("column-") || nodeId.startsWith("map-group-");
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

function edgeColor(primary: boolean, related: boolean): string {
  if (primary) {
    return "rgba(130, 143, 255, 0.92)";
  }
  if (related) {
    return "rgba(138, 143, 152, 0.62)";
  }
  return "rgba(98, 102, 109, 0.32)";
}
