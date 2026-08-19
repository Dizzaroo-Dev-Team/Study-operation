// builder/layout.ts
// Tidy top-down auto-layout for the workflow canvas. The old builder placed nodes
// in a naive zigzag (x = 220 + (i%2)*260, y = 80 + i*130), which spread steps far
// apart and made `fitView` zoom way out — the "flowchart becomes tiny" bug.
//
// Here we run dagre (the standard React Flow layout engine) to produce a clean
// layered graph: start at the top, arrows flow downward, siblings spread sideways.
// Pure function — takes nodes + edges, returns the SAME nodes with new positions.

import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

// Keep these in sync with the rendered StepNode footprint so dagre reserves the
// right gaps. Slightly generous so edges/labels never overlap a box.
export const NODE_W = 210;
export const NODE_H = 84;

export interface LayoutOptions {
  /** "TB" top→bottom (default) or "LR" left→right. */
  direction?: "TB" | "LR";
  /** Gap between ranks (rows in TB). */
  rankSep?: number;
  /** Gap between nodes in the same rank. */
  nodeSep?: number;
}

export function layoutGraph(
  nodes: Node[],
  edges: Edge[],
  opts: LayoutOptions = {},
): Node[] {
  if (nodes.length === 0) return nodes;
  const { direction = "TB", rankSep = 90, nodeSep = 60 } = opts;

  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: direction, ranksep: rankSep, nodesep: nodeSep, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(() => ({}));

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => {
    // Only lay out edges whose endpoints both exist (defensive against stale edges).
    if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target);
  });

  dagre.layout(g);

  return nodes.map((n) => {
    const p = g.node(n.id);
    if (!p) return n;
    // dagre returns the node CENTER; React Flow positions by top-left corner.
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}
