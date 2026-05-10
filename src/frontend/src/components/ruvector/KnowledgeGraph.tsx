import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactFlow, {
  Node,
  Edge,
  Controls,
  MiniMap,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  NodeProps,
  Handle,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Lightbulb,
  CheckSquare,
  HelpCircle,
  Zap,
  MessageSquare,
  BookOpen,
  Link as LinkIcon,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { api } from "@/api/client";

// Types
interface GraphNode {
  id: string;
  content: string;
  unit_type: string;
  source_channel: string | null;
  source_date: string | null;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  edge_type: string;
  weight: number;
}

interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
}

// Node colors by type
const nodeColors: Record<string, { bg: string; border: string; text: string }> = {
  claim: { bg: "#fef3c7", border: "#f59e0b", text: "#92400e" },
  decision: { bg: "#d1fae5", border: "#10b981", text: "#065f46" },
  question: { bg: "#dbeafe", border: "#3b82f6", text: "#1e40af" },
  action_item: { bg: "#fed7aa", border: "#f97316", text: "#9a3412" },
  context: { bg: "#ede9fe", border: "#8b5cf6", text: "#5b21b6" },
  definition: { bg: "#e0e7ff", border: "#6366f1", text: "#3730a3" },
  reference: { bg: "#cffafe", border: "#06b6d4", text: "#155e75" },
};

// Edge colors by type
const edgeColors: Record<string, string> = {
  relates_to: "#9ca3af",
  supports: "#10b981",
  contradicts: "#ef4444",
  answers: "#3b82f6",
  depends_on: "#8b5cf6",
  supersedes: "#f59e0b",
  implements: "#6366f1",
};

// Edge styles
const edgeStyles: Record<string, string> = {
  relates_to: "dashed",
  supports: "solid",
  contradicts: "dotted",
  answers: "solid",
  depends_on: "solid",
  supersedes: "solid",
  implements: "solid",
};

// Node icons
const nodeIcons: Record<string, React.ReactNode> = {
  claim: <Lightbulb className="h-3 w-3" />,
  decision: <CheckSquare className="h-3 w-3" />,
  question: <HelpCircle className="h-3 w-3" />,
  action_item: <Zap className="h-3 w-3" />,
  context: <MessageSquare className="h-3 w-3" />,
  definition: <BookOpen className="h-3 w-3" />,
  reference: <LinkIcon className="h-3 w-3" />,
};

// Custom node component
function KnowledgeNode({ data }: NodeProps) {
  const colors = nodeColors[data.unit_type] || { bg: "#f3f4f6", border: "#9ca3af", text: "#374151" };
  const icon = nodeIcons[data.unit_type] || <AlertCircle className="h-3 w-3" />;

  return (
    <div
      className="px-3 py-2 rounded-lg border-2 shadow-sm max-w-[200px] cursor-pointer hover:shadow-md transition-shadow"
      style={{
        backgroundColor: colors.bg,
        borderColor: colors.border,
        color: colors.text,
      }}
    >
      <Handle type="target" position={Position.Top} className="!bg-gray-400" />
      <div className="flex items-start gap-2">
        <div className="flex-shrink-0 mt-0.5">{icon}</div>
        <p className="text-xs leading-tight line-clamp-3">{data.content}</p>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-gray-400" />
    </div>
  );
}

const nodeTypes = {
  knowledge: KnowledgeNode,
};

// API function
async function fetchGraph(
  guildId: string,
  limit: number,
  unitTypes?: string
): Promise<GraphResponse> {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (unitTypes && unitTypes !== "all") {
    params.append("unit_types", unitTypes);
  }
  return api.get<GraphResponse>(`/ruvector/guilds/${guildId}/graph?${params.toString()}`);
}

// Force-directed layout using simple physics simulation
function layoutNodes(graphNodes: GraphNode[], graphEdges: GraphEdge[]): Node[] {
  const width = 800;
  const height = 600;
  const nodeMap = new Map<string, { x: number; y: number; vx: number; vy: number }>();

  // Initialize positions randomly
  graphNodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / graphNodes.length;
    const radius = Math.min(width, height) * 0.3;
    nodeMap.set(node.id, {
      x: width / 2 + radius * Math.cos(angle) + (Math.random() - 0.5) * 100,
      y: height / 2 + radius * Math.sin(angle) + (Math.random() - 0.5) * 100,
      vx: 0,
      vy: 0,
    });
  });

  // Run simulation iterations
  const iterations = 50;
  const repulsion = 5000;
  const attraction = 0.05;
  const damping = 0.9;

  for (let iter = 0; iter < iterations; iter++) {
    // Repulsion between all nodes
    for (const nodeA of graphNodes) {
      const posA = nodeMap.get(nodeA.id)!;
      for (const nodeB of graphNodes) {
        if (nodeA.id === nodeB.id) continue;
        const posB = nodeMap.get(nodeB.id)!;
        const dx = posA.x - posB.x;
        const dy = posA.y - posB.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = repulsion / (dist * dist);
        posA.vx += (dx / dist) * force;
        posA.vy += (dy / dist) * force;
      }
    }

    // Attraction along edges
    for (const edge of graphEdges) {
      const posA = nodeMap.get(edge.source);
      const posB = nodeMap.get(edge.target);
      if (!posA || !posB) continue;
      const dx = posB.x - posA.x;
      const dy = posB.y - posA.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      posA.vx += dx * attraction;
      posA.vy += dy * attraction;
      posB.vx -= dx * attraction;
      posB.vy -= dy * attraction;
    }

    // Apply velocity and damping
    for (const node of graphNodes) {
      const pos = nodeMap.get(node.id)!;
      pos.x += pos.vx;
      pos.y += pos.vy;
      pos.vx *= damping;
      pos.vy *= damping;

      // Keep in bounds
      pos.x = Math.max(50, Math.min(width - 50, pos.x));
      pos.y = Math.max(50, Math.min(height - 50, pos.y));
    }
  }

  // Convert to React Flow nodes
  return graphNodes.map((node) => {
    const pos = nodeMap.get(node.id)!;
    return {
      id: node.id,
      type: "knowledge",
      position: { x: pos.x, y: pos.y },
      data: {
        content: node.content,
        unit_type: node.unit_type,
        source_channel: node.source_channel,
        source_date: node.source_date,
      },
    };
  });
}

// Convert graph edges to React Flow edges
function convertEdges(graphEdges: GraphEdge[]): Edge[] {
  return graphEdges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: "default",
    animated: edge.edge_type === "supports",
    style: {
      stroke: edgeColors[edge.edge_type] || "#9ca3af",
      strokeWidth: Math.max(1, edge.weight * 2),
      strokeDasharray: edgeStyles[edge.edge_type] === "dashed" ? "5,5" : edgeStyles[edge.edge_type] === "dotted" ? "2,2" : undefined,
    },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: edgeColors[edge.edge_type] || "#9ca3af",
    },
    data: { edge_type: edge.edge_type },
  }));
}

interface KnowledgeGraphProps {
  guildId: string;
}

export function KnowledgeGraph({ guildId }: KnowledgeGraphProps) {
  const [limit, setLimit] = useState(100);
  const [unitTypeFilter, setUnitTypeFilter] = useState("all");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["ruvector-graph", guildId, limit, unitTypeFilter],
    queryFn: () => fetchGraph(guildId, limit, unitTypeFilter),
  });

  const initialNodes = useMemo(() => {
    if (!data) return [];
    return layoutNodes(data.nodes, data.edges);
  }, [data]);

  const initialEdges = useMemo(() => {
    if (!data) return [];
    return convertEdges(data.edges);
  }, [data]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes/edges when data changes
  useMemo(() => {
    if (initialNodes.length > 0) {
      setNodes(initialNodes);
    }
    if (initialEdges.length > 0) {
      setEdges(initialEdges);
    }
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const graphNode = data?.nodes.find((n) => n.id === node.id);
      setSelectedNode(graphNode || null);
    },
    [data]
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[500px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-lg bg-destructive/10 text-destructive">
        Failed to load graph: {(error as Error).message}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Nodes:</span>
          <div className="w-32">
            <Slider
              value={[limit]}
              onValueChange={([v]) => setLimit(v)}
              min={10}
              max={500}
              step={10}
            />
          </div>
          <span className="text-sm w-12">{limit}</span>
        </div>

        <Select value={unitTypeFilter} onValueChange={setUnitTypeFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            <SelectItem value="claim">Claims</SelectItem>
            <SelectItem value="decision">Decisions</SelectItem>
            <SelectItem value="question">Questions</SelectItem>
            <SelectItem value="action_item">Action Items</SelectItem>
            <SelectItem value="context">Context</SelectItem>
            <SelectItem value="definition">Definitions</SelectItem>
            <SelectItem value="reference">References</SelectItem>
          </SelectContent>
        </Select>

        <div className="text-sm text-muted-foreground">
          Showing {data?.nodes.length || 0} of {data?.total_nodes || 0} nodes,{" "}
          {data?.edges.length || 0} of {data?.total_edges || 0} edges
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs">
        <span className="text-muted-foreground">Node types:</span>
        {Object.entries(nodeColors).map(([type, colors]) => (
          <div key={type} className="flex items-center gap-1">
            <div
              className="w-3 h-3 rounded border"
              style={{ backgroundColor: colors.bg, borderColor: colors.border }}
            />
            <span className="capitalize">{type.replace(/_/g, " ")}</span>
          </div>
        ))}
      </div>

      <div className="flex gap-4">
        {/* Graph */}
        <div className="flex-1 h-[500px] border rounded-lg bg-gray-50 dark:bg-gray-900">
          {data && data.nodes.length > 0 ? (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              nodeTypes={nodeTypes}
              fitView
              attributionPosition="bottom-left"
            >
              <Controls />
              <MiniMap
                nodeColor={(node) => nodeColors[node.data?.unit_type]?.border || "#9ca3af"}
                maskColor="rgb(0, 0, 0, 0.1)"
              />
              <Background color="#e5e7eb" gap={16} />
            </ReactFlow>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              No knowledge units found. Run a summary with inline extraction to populate the graph.
            </div>
          )}
        </div>

        {/* Selected node detail */}
        {selectedNode && (
          <Card className="w-80 flex-shrink-0">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <Badge
                  style={{
                    backgroundColor: nodeColors[selectedNode.unit_type]?.bg,
                    color: nodeColors[selectedNode.unit_type]?.text,
                    borderColor: nodeColors[selectedNode.unit_type]?.border,
                  }}
                >
                  {selectedNode.unit_type.replace(/_/g, " ")}
                </Badge>
                <button
                  onClick={() => setSelectedNode(null)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  &times;
                </button>
              </div>
              <CardTitle className="text-sm font-medium mt-2">
                {selectedNode.source_channel && `#${selectedNode.source_channel}`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-48">
                <p className="text-sm">{selectedNode.content}</p>
              </ScrollArea>
              {selectedNode.source_date && (
                <p className="text-xs text-muted-foreground mt-2">
                  {new Date(selectedNode.source_date).toLocaleDateString()}
                </p>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

export default KnowledgeGraph;
