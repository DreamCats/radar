import { Position, type Edge as FlowEdge, type Node as FlowNode } from "@xyflow/react";

import type { IndustryChainData, IndustryChainEdge } from "../types";
import { FlowNodeLabel, MAP_ROOT_ID, buildGraphEdges, mapGroupId, type GraphColumn } from "./IndustryChainGraphShared";

type GraphLayout = {
  center: { x: number; y: number };
  label: { x: number; y: number };
};

export function buildKnowledgeGraphNodes(
  data: IndustryChainData,
  selectedNodeId: string | undefined,
  activeNodeIds: Set<string>,
  relatedNodeIds: Set<string>,
  columns: GraphColumn[],
): FlowNode[] {
  const layouts = buildKnowledgeGraphLayouts(columns);
  const rootNode: FlowNode = {
    id: MAP_ROOT_ID,
    position: { x: -82, y: -54 },
    data: { label: <MapRootLabel data={data} /> },
    className: "industry-chain-map-root",
    draggable: false,
    selectable: false,
  };
  const groupNodes = columns.map((column) => {
    const layout = layouts.get(column.key) ?? { center: { x: 0, y: 0 }, label: { x: 0, y: 0 } };
    return {
      id: mapGroupId(column.key),
      position: layout.label,
      data: { label: <MapGroupLabel column={column} /> },
      className: "industry-chain-map-group-label",
      draggable: false,
      selectable: false,
    };
  });
  const chainNodes = data.nodes.map((node) => {
    const column = columns.find((item) => item.nodeIds.includes(node.id)) ?? columns[0];
    const columnLayout = layouts.get(column.key) ?? { center: { x: 0, y: 0 }, label: { x: 0, y: 0 } };
    const nodeIndex = Math.max(0, column.nodeIds.indexOf(node.id));
    const selected = node.id === selectedNodeId;
    const active = activeNodeIds.has(node.id);
    const related = relatedNodeIds.has(node.id);
    const dimmed = activeNodeIds.size > 0 && !active && !related && !selected;
    return {
      id: node.id,
      position: mapNodePosition(columnLayout.center, nodeIndex, column.nodeIds.length),
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: { label: <FlowNodeLabel node={node} /> },
      className: [
        "industry-chain-flow-node",
        "knowledge-node",
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
  return [rootNode, ...groupNodes, ...chainNodes];
}

export function buildKnowledgeGraphEdges(
  data: IndustryChainData,
  selectedNodeId: string | undefined,
  activeNodeIds: Set<string>,
  relatedEdges: IndustryChainEdge[],
  columns: GraphColumn[],
): FlowEdge[] {
  const groupEdges: FlowEdge[] = columns.map((column) => ({
    id: `${MAP_ROOT_ID}-${mapGroupId(column.key)}`,
    source: MAP_ROOT_ID,
    target: mapGroupId(column.key),
    type: "straight",
    selectable: false,
    style: { stroke: "rgba(138, 143, 152, 0.22)", strokeDasharray: "5 6", strokeWidth: 1.2 },
  }));
  return [
    ...groupEdges,
    ...buildGraphEdges(data, selectedNodeId, activeNodeIds, relatedEdges).map((edge) => ({
      ...edge,
      type: "straight",
      style: {
        ...edge.style,
        strokeWidth: typeof edge.style?.strokeWidth === "number" ? Math.max(edge.style.strokeWidth, 1.55) : 1.55,
      },
    })),
  ];
}

function buildKnowledgeGraphLayouts(columns: GraphColumn[]): Map<string, GraphLayout> {
  const anchors = [
    { x: -410, y: -80 },
    { x: -210, y: -260 },
    { x: 180, y: -260 },
    { x: 410, y: -80 },
    { x: 200, y: 210 },
    { x: -230, y: 210 },
    { x: 0, y: 330 },
  ];
  const layouts = new Map<string, GraphLayout>();
  columns.forEach((column, index) => {
    const anchor = anchors[index] ?? circularAnchor(index, columns.length);
    layouts.set(column.key, {
      center: anchor,
      label: { x: anchor.x - 84, y: clusterTopY(anchor, column.nodeIds.length) - 54 },
    });
  });
  return layouts;
}

function clusterTopY(center: { x: number; y: number }, count: number): number {
  if (count <= 1) {
    return center.y;
  }
  if (count === 2) {
    return center.y - 58;
  }
  if (count === 3) {
    return center.y - 78;
  }
  return center.y - Math.ceil(count / 2) * 58;
}

function circularAnchor(index: number, total: number): { x: number; y: number } {
  const angle = -Math.PI / 2 + (index / Math.max(total, 1)) * Math.PI * 2;
  return { x: Math.cos(angle) * 370, y: Math.sin(angle) * 250 };
}

function mapNodePosition(center: { x: number; y: number }, index: number, total: number): { x: number; y: number } {
  if (total <= 1) {
    return { x: center.x - 84, y: center.y - 45 };
  }
  if (total === 2) {
    return { x: center.x - 84, y: center.y + (index === 0 ? -104 : 12) };
  }
  if (total === 3) {
    const offsets = [
      { x: 0, y: -126 },
      { x: -96, y: 0 },
      { x: 96, y: 0 },
    ];
    const offset = offsets[index] ?? offsets[0];
    return { x: center.x - 84 + offset.x, y: center.y - 45 + offset.y };
  }
  const columns = total >= 6 ? 3 : 2;
  const column = index % columns;
  const row = Math.floor(index / columns);
  const xGap = 184;
  const yGap = 112;
  const startX = -((columns - 1) * xGap) / 2;
  const startY = -((Math.ceil(total / columns) - 1) * yGap) / 2;
  return { x: center.x - 84 + startX + column * xGap, y: center.y - 45 + startY + row * yGap };
}

function MapRootLabel({ data }: { data: IndustryChainData }) {
  return (
    <div className="industry-chain-map-root-label">
      <span>{data.title}</span>
      <em>{data.category}</em>
      <b>{data.nodes.length} 节点</b>
    </div>
  );
}

function MapGroupLabel({ column }: { column: GraphColumn }) {
  return (
    <div className="industry-chain-map-group-label-inner">
      <span>{column.label}</span>
      <em>{column.description}</em>
    </div>
  );
}
