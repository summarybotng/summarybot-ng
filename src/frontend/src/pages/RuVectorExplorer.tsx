import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Database,
  Search,
  List,
  BarChart3,
  Loader2,
  Hash,
  Calendar,
  Tag,
  Lightbulb,
  CheckSquare,
  HelpCircle,
  MessageSquare,
  BookOpen,
  Link as LinkIcon,
  AlertCircle,
  Clock,
  Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/api/client";

// Types
interface KnowledgeUnit {
  id: string;
  content: string;
  unit_type: string;
  score: number;
  source_id: string;
  source_channel: string | null;
  source_date: string | null;
}

interface SemanticSearchResponse {
  query: string;
  guild_id: string;
  total: number;
  units: KnowledgeUnit[];
  search_time_ms: number;
}

interface RuVectorStats {
  guild_id: string;
  total_units: number;
  units_by_type: Record<string, number>;
  total_edges: number;
  edges_by_type: Record<string, number>;
  total_signals: number;
  units_with_embeddings: number;
}

// Unit type icons
const unitTypeIcons: Record<string, React.ReactNode> = {
  claim: <Lightbulb className="h-4 w-4 text-yellow-500" />,
  decision: <CheckSquare className="h-4 w-4 text-green-500" />,
  question: <HelpCircle className="h-4 w-4 text-blue-500" />,
  action_item: <Zap className="h-4 w-4 text-orange-500" />,
  context: <MessageSquare className="h-4 w-4 text-purple-500" />,
  definition: <BookOpen className="h-4 w-4 text-indigo-500" />,
  reference: <LinkIcon className="h-4 w-4 text-cyan-500" />,
};

const unitTypeLabels: Record<string, string> = {
  claim: "Claim",
  decision: "Decision",
  question: "Question",
  action_item: "Action Item",
  context: "Context",
  definition: "Definition",
  reference: "Reference",
};

// API functions
async function fetchStats(guildId: string): Promise<RuVectorStats> {
  return api.get<RuVectorStats>(`/ruvector/guilds/${guildId}/stats`);
}

async function searchUnits(
  guildId: string,
  query: string,
  limit: number = 20,
  unitTypes?: string
): Promise<SemanticSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: limit.toString() });
  if (unitTypes) params.append("unit_types", unitTypes);
  return api.get<SemanticSearchResponse>(`/ruvector/guilds/${guildId}/search?${params.toString()}`);
}

async function listUnits(
  guildId: string,
  limit: number = 50,
  unitType?: string
): Promise<SemanticSearchResponse> {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (unitType) params.append("unit_type", unitType);
  return api.get<SemanticSearchResponse>(`/ruvector/guilds/${guildId}/units?${params.toString()}`);
}

// Components
function StatsOverview({ stats }: { stats: RuVectorStats }) {
  const embeddingPercent = stats.total_units > 0
    ? ((stats.units_with_embeddings / stats.total_units) * 100).toFixed(1)
    : "0";

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-primary" />
            <span className="text-sm text-muted-foreground">Total Units</span>
          </div>
          <div className="text-3xl font-bold mt-2">
            {stats.total_units.toLocaleString()}
          </div>
          <p className="text-xs text-muted-foreground mt-1">Knowledge units stored</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <LinkIcon className="h-5 w-5 text-blue-500" />
            <span className="text-sm text-muted-foreground">Edges</span>
          </div>
          <div className="text-3xl font-bold mt-2">
            {stats.total_edges.toLocaleString()}
          </div>
          <p className="text-xs text-muted-foreground mt-1">Relationships between units</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <Search className="h-5 w-5 text-green-500" />
            <span className="text-sm text-muted-foreground">Embeddings</span>
          </div>
          <div className="text-3xl font-bold mt-2">{embeddingPercent}%</div>
          <p className="text-xs text-muted-foreground mt-1">
            {stats.units_with_embeddings.toLocaleString()} with vectors
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-orange-500" />
            <span className="text-sm text-muted-foreground">Signals</span>
          </div>
          <div className="text-3xl font-bold mt-2">
            {stats.total_signals.toLocaleString()}
          </div>
          <p className="text-xs text-muted-foreground mt-1">Feedback signals collected</p>
        </CardContent>
      </Card>
    </div>
  );
}

function UnitTypeBreakdown({ stats }: { stats: RuVectorStats }) {
  const types = Object.entries(stats.units_by_type).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...types.map(([, count]) => count), 1);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Tag className="h-5 w-5" />
          Units by Type
        </CardTitle>
        <CardDescription>Distribution of knowledge unit types</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {types.map(([type, count]) => (
            <div key={type} className="flex items-center gap-3">
              <div className="w-8 flex justify-center">
                {unitTypeIcons[type] || <AlertCircle className="h-4 w-4 text-muted-foreground" />}
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="font-medium">{unitTypeLabels[type] || type}</span>
                  <span className="text-muted-foreground">{count.toLocaleString()}</span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
          {types.length === 0 && (
            <p className="text-center text-muted-foreground py-4">
              No knowledge units found
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function EdgeTypeBreakdown({ stats }: { stats: RuVectorStats }) {
  const edges = Object.entries(stats.edges_by_type).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...edges.map(([, count]) => count), 1);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <LinkIcon className="h-5 w-5" />
          Edges by Type
        </CardTitle>
        <CardDescription>Relationship types between units</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {edges.map(([type, count]) => (
            <div key={type} className="flex items-center gap-3">
              <div className="flex-1">
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="font-medium capitalize">{type.replace(/_/g, " ")}</span>
                  <span className="text-muted-foreground">{count.toLocaleString()}</span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
          {edges.length === 0 && (
            <p className="text-center text-muted-foreground py-4">
              No edges found
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function KnowledgeUnitCard({ unit }: { unit: KnowledgeUnit }) {
  return (
    <div className="p-4 rounded-lg border hover:bg-accent/50 transition-colors">
      <div className="flex items-start gap-3">
        <div className="mt-1">
          {unitTypeIcons[unit.unit_type] || <AlertCircle className="h-4 w-4 text-muted-foreground" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm leading-relaxed">{unit.content}</p>
          <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
            <Badge variant="secondary" className="text-xs">
              {unitTypeLabels[unit.unit_type] || unit.unit_type}
            </Badge>
            {unit.source_channel && (
              <span className="flex items-center gap-1">
                <Hash className="h-3 w-3" />
                {unit.source_channel}
              </span>
            )}
            {unit.source_date && (
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {new Date(unit.source_date).toLocaleDateString()}
              </span>
            )}
            {unit.score > 0 && unit.score < 1 && (
              <span className="flex items-center gap-1">
                <Search className="h-3 w-3" />
                {(unit.score * 100).toFixed(0)}% match
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SearchTab({ guildId }: { guildId: string }) {
  const [query, setQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [unitTypeFilter, setUnitTypeFilter] = useState<string>("all");

  const { data, isLoading, error } = useQuery({
    queryKey: ["ruvector-search", guildId, searchQuery, unitTypeFilter],
    queryFn: () =>
      searchUnits(guildId, searchQuery, 30, unitTypeFilter !== "all" ? unitTypeFilter : undefined),
    enabled: !!searchQuery,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      setSearchQuery(query.trim());
    }
  };

  return (
    <div className="space-y-4">
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search knowledge units semantically..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-10"
          />
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
        <Button type="submit" disabled={isLoading || !query.trim()}>
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Search"}
        </Button>
      </form>

      {error && (
        <div className="p-4 rounded-lg bg-destructive/10 text-destructive text-sm">
          Search failed: {(error as Error).message}
        </div>
      )}

      {data && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Found {data.total} result{data.total !== 1 ? "s" : ""} for "{data.query}"
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {data.search_time_ms}ms
            </span>
          </div>
          <ScrollArea className="h-[500px]">
            <div className="space-y-2">
              {data.units.map((unit) => (
                <KnowledgeUnitCard key={unit.id} unit={unit} />
              ))}
              {data.units.length === 0 && (
                <p className="text-center text-muted-foreground py-8">
                  No matching knowledge units found
                </p>
              )}
            </div>
          </ScrollArea>
        </div>
      )}

      {!searchQuery && (
        <div className="text-center text-muted-foreground py-12">
          <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>Enter a query to search semantically across knowledge units</p>
          <p className="text-sm mt-2">
            Try searching for topics, concepts, or questions
          </p>
        </div>
      )}
    </div>
  );
}

function BrowseTab({ guildId }: { guildId: string }) {
  const [unitTypeFilter, setUnitTypeFilter] = useState<string>("all");
  const [limit, setLimit] = useState(50);

  const { data, isLoading } = useQuery({
    queryKey: ["ruvector-browse", guildId, unitTypeFilter, limit],
    queryFn: () => listUnits(guildId, limit, unitTypeFilter !== "all" ? unitTypeFilter : undefined),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
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
        <Select value={limit.toString()} onValueChange={(v) => setLimit(parseInt(v))}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="Limit" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="25">25 units</SelectItem>
            <SelectItem value="50">50 units</SelectItem>
            <SelectItem value="100">100 units</SelectItem>
            <SelectItem value="200">200 units</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : (
        <ScrollArea className="h-[500px]">
          <div className="space-y-2">
            {data?.units.map((unit) => (
              <KnowledgeUnitCard key={unit.id} unit={unit} />
            ))}
            {(!data || data.units.length === 0) && (
              <p className="text-center text-muted-foreground py-8">
                No knowledge units found
              </p>
            )}
          </div>
        </ScrollArea>
      )}

      {data && (
        <div className="text-sm text-muted-foreground">
          Showing {data.units.length} of {data.total} units
        </div>
      )}
    </div>
  );
}

export function RuVectorExplorer() {
  const { id: guildId } = useParams<{ id: string }>();

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["ruvector-stats", guildId],
    queryFn: () => fetchStats(guildId!),
    enabled: !!guildId,
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        <Database className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">RuVector Explorer</h1>
          <p className="text-sm text-muted-foreground">
            Browse and search the semantic knowledge store (ADR-090)
          </p>
        </div>
      </div>

      {/* Stats Overview */}
      {statsLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      ) : stats ? (
        <StatsOverview stats={stats} />
      ) : null}

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Search/Browse tabs */}
        <div className="lg:col-span-2">
          <Tabs defaultValue="search">
            <TabsList>
              <TabsTrigger value="search" className="flex items-center gap-2">
                <Search className="h-4 w-4" />
                Semantic Search
              </TabsTrigger>
              <TabsTrigger value="browse" className="flex items-center gap-2">
                <List className="h-4 w-4" />
                Browse
              </TabsTrigger>
            </TabsList>

            <TabsContent value="search" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Semantic Search</CardTitle>
                  <CardDescription>
                    Search knowledge units using natural language
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {guildId && <SearchTab guildId={guildId} />}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="browse" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Browse Units</CardTitle>
                  <CardDescription>
                    View knowledge units by type
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {guildId && <BrowseTab guildId={guildId} />}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        {/* Right: Breakdowns */}
        <div className="space-y-6">
          {statsLoading ? (
            <>
              <Skeleton className="h-64" />
              <Skeleton className="h-64" />
            </>
          ) : stats ? (
            <>
              <UnitTypeBreakdown stats={stats} />
              <EdgeTypeBreakdown stats={stats} />
            </>
          ) : null}
        </div>
      </div>
    </motion.div>
  );
}

export default RuVectorExplorer;
