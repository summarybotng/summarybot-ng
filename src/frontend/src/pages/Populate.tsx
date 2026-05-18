import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/hooks/use-toast";
import {
  FileText,
  AlertTriangle,
  RefreshCw,
  Loader2,
  Sparkles,
  Cpu,
  Eye,
  Play,
  Square,
  X,
  ArrowDownToLine,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { api } from "@/api/client";

// Types
interface WikiStats {
  total_pages: number;
  total_sources: number;
  categories: Record<string, number>;
}

interface WikiSettings {
  wiki_auto_ingest: boolean;
  wiki_auto_synthesis: boolean;
  wiki_ingest_to_vectors: boolean;
  wiki_allowed_perspectives: string[];
  wiki_synthesis_job_enabled: boolean;
  wiki_synthesis_job_last_run: string | null;
  wiki_synthesis_job_interval_hours: number;
  dirty_page_count: number;
}

interface WikiAvailablePerspectives {
  available: string[];
  allowed: string[];
  counts: Record<string, number>;
}

interface BackfillRequest {
  mode: "unprocessed" | "all" | "date_range";
  batch_size?: number;
  delay_between_batches?: number;
  date_from?: string;
  date_to?: string;
  update_threshold?: number;
}

interface BackfillJobResponse {
  job_id: string;
  status: string;
  total_summaries: number;
  message: string;
}

interface BackfillStatus {
  job_id: string;
  status: string;
  progress_current: number;
  progress_total: number;
  progress_message: string;
  stats: {
    ingested: number;
    skipped: number;
    failed: number;
  };
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

interface ClearWikiResult {
  pages_deleted: number;
  sources_deleted: number;
}

interface ClearRuVectorResult {
  success: boolean;
  deleted_count: number;
  message: string;
}

// API functions
async function fetchWikiStats(guildId: string): Promise<WikiStats> {
  return api.get<WikiStats>(`/guilds/${guildId}/wiki/stats`);
}

async function fetchWikiSettings(guildId: string): Promise<WikiSettings> {
  return api.get<WikiSettings>(`/guilds/${guildId}/wiki/settings`);
}

async function updateWikiSettings(guildId: string, settings: Partial<WikiSettings>): Promise<WikiSettings> {
  return api.patch<WikiSettings>(`/guilds/${guildId}/wiki/settings`, settings);
}

async function fetchAvailablePerspectives(guildId: string): Promise<WikiAvailablePerspectives> {
  return api.get<WikiAvailablePerspectives>(`/guilds/${guildId}/wiki/available-perspectives`);
}

async function startBackfill(guildId: string, request: BackfillRequest): Promise<BackfillJobResponse> {
  return api.post<BackfillJobResponse>(`/guilds/${guildId}/wiki/backfill`, request);
}

async function getBackfillStatus(guildId: string): Promise<BackfillStatus | null> {
  try {
    return await api.get<BackfillStatus>(`/guilds/${guildId}/wiki/backfill/status`);
  } catch {
    return null;
  }
}

async function cancelBackfill(guildId: string): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>(`/guilds/${guildId}/wiki/backfill/cancel`, {});
}

async function clearWiki(guildId: string): Promise<ClearWikiResult> {
  return api.delete<ClearWikiResult>(`/guilds/${guildId}/wiki`);
}

async function clearRuVector(guildId: string): Promise<ClearRuVectorResult> {
  return api.delete<ClearRuVectorResult>(`/ruvector/guilds/${guildId}/clear?confirm=true`);
}

export function Populate() {
  const { id: guildId } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [showClearRuVectorConfirm, setShowClearRuVectorConfirm] = useState(false);
  const [backfillMode, setBackfillMode] = useState<"unprocessed" | "all">("unprocessed");
  const [updateThreshold, setUpdateThreshold] = useState(2);

  // Fetch stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["wiki-stats", guildId],
    queryFn: () => fetchWikiStats(guildId!),
    enabled: !!guildId,
  });

  // Fetch available perspectives
  const { data: perspectivesData } = useQuery({
    queryKey: ["wiki-perspectives", guildId],
    queryFn: () => fetchAvailablePerspectives(guildId!),
    enabled: !!guildId,
  });

  // Fetch wiki settings for perspective management
  const { data: wikiSettings } = useQuery({
    queryKey: ["wiki-settings", guildId],
    queryFn: () => fetchWikiSettings(guildId!),
    enabled: !!guildId,
  });

  // Update settings mutation
  const settingsMutation = useMutation({
    mutationFn: (settings: Partial<WikiSettings>) => updateWikiSettings(guildId!, settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["wiki-settings", guildId] });
      toast({ title: "Settings saved" });
    },
    onError: () => {
      toast({ title: "Failed to save settings", variant: "destructive" });
    },
  });

  // Toggle perspective
  const togglePerspective = (perspective: string) => {
    const current = wikiSettings?.wiki_allowed_perspectives || ["general"];
    const newPerspectives = current.includes(perspective)
      ? current.filter(p => p !== perspective)
      : [...current, perspective];
    if (newPerspectives.length === 0) {
      toast({ title: "At least one perspective must be selected", variant: "destructive" });
      return;
    }
    settingsMutation.mutate({ wiki_allowed_perspectives: newPerspectives });
  };

  // Fetch backfill status (poll every 3s when active)
  const { data: backfillStatus, refetch: refetchBackfill } = useQuery({
    queryKey: ["wiki-backfill-status", guildId],
    queryFn: () => getBackfillStatus(guildId!),
    enabled: !!guildId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "pending" || status === "paused" ? 3000 : false;
    },
  });

  const isBackfillActive = backfillStatus?.status === "running" || backfillStatus?.status === "pending";
  const isBackfillPaused = backfillStatus?.status === "paused";

  // Start backfill mutation
  const startBackfillMutation = useMutation({
    mutationFn: (params: { mode: "unprocessed" | "all"; updateThreshold: number }) => startBackfill(guildId!, {
      mode: params.mode,
      batch_size: 10,
      delay_between_batches: 1.0,
      update_threshold: params.updateThreshold,
    }),
    onSuccess: (data) => {
      refetchBackfill();
      toast({
        title: "Backfill started",
        description: data.message,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to start backfill",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Cancel backfill mutation
  const cancelBackfillMutation = useMutation({
    mutationFn: () => cancelBackfill(guildId!),
    onSuccess: () => {
      refetchBackfill();
      queryClient.invalidateQueries({ queryKey: ["wiki-stats", guildId] });
      toast({ title: "Backfill cancelled" });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to cancel backfill",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Clear wiki mutation
  const clearMutation = useMutation({
    mutationFn: () => clearWiki(guildId!),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["wiki-tree", guildId] });
      queryClient.invalidateQueries({ queryKey: ["wiki-stats", guildId] });
      queryClient.invalidateQueries({ queryKey: ["wiki-recent", guildId] });
      setShowClearConfirm(false);
      toast({
        title: "Wiki cleared",
        description: `Deleted ${data.pages_deleted} pages and ${data.sources_deleted} sources`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to clear wiki",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Clear RuVector mutation
  const clearRuVectorMutation = useMutation({
    mutationFn: () => clearRuVector(guildId!),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["ruvector-stats", guildId] });
      setShowClearRuVectorConfirm(false);
      toast({
        title: "RuVector cleared",
        description: data.message,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to clear RuVector",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Calculate backfill progress percentage
  const backfillPercent = backfillStatus?.progress_total
    ? Math.round((backfillStatus.progress_current / backfillStatus.progress_total) * 100)
    : 0;

  if (!guildId) return null;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <ArrowDownToLine className="h-6 w-6" />
        <div>
          <h1 className="text-2xl font-bold">Populate Knowledge</h1>
          <p className="text-muted-foreground">
            Backfill Wiki pages and RuVector knowledge units from existing summaries
          </p>
        </div>
      </div>

      {/* Stats Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            Wiki Statistics
          </CardTitle>
        </CardHeader>
        <CardContent>
          {statsLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </div>
          ) : stats ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-2xl font-bold">{stats.total_pages}</div>
                <div className="text-sm text-muted-foreground">Total Pages</div>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-2xl font-bold">{stats.total_sources}</div>
                <div className="text-sm text-muted-foreground">Sources</div>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-2xl font-bold">{stats.categories?.topics || 0}</div>
                <div className="text-sm text-muted-foreground">Topics</div>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-2xl font-bold">{stats.categories?.decisions || 0}</div>
                <div className="text-sm text-muted-foreground">Decisions</div>
              </div>
            </div>
          ) : (
            <p className="text-muted-foreground">No wiki data yet</p>
          )}
        </CardContent>
      </Card>

      {/* Ingestion Settings Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            Ingestion Settings
          </CardTitle>
          <CardDescription>
            Configure what gets populated when new summaries are created
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Ingestion path toggles */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Ingestion Paths</label>

            {/* Pages toggle */}
            <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="text-sm font-medium">Wiki Pages</span>
                  <p className="text-xs text-muted-foreground">Summaries update wiki page content</p>
                </div>
              </div>
              <Switch
                checked={wikiSettings?.wiki_auto_ingest ?? true}
                onCheckedChange={(checked) => settingsMutation.mutate({ wiki_auto_ingest: checked })}
                disabled={settingsMutation.isPending}
              />
            </div>

            {/* Vectors toggle */}
            <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="text-sm font-medium">RuVector Knowledge Units</span>
                  <p className="text-xs text-muted-foreground">Summaries create knowledge units for semantic search</p>
                </div>
              </div>
              <Switch
                checked={wikiSettings?.wiki_ingest_to_vectors ?? false}
                onCheckedChange={(checked) => settingsMutation.mutate({ wiki_ingest_to_vectors: checked })}
                disabled={settingsMutation.isPending}
              />
            </div>

            <p className="text-xs text-muted-foreground">
              Enable both to populate Wiki and RuVector simultaneously from new summaries.
            </p>
          </div>

          {/* Perspective selector */}
          <div className="space-y-3">
            <label className="text-sm font-medium">Allowed Perspectives</label>
            {perspectivesData?.available && perspectivesData.available.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {perspectivesData.available.map((perspective) => {
                  const isAllowed = wikiSettings?.wiki_allowed_perspectives?.includes(perspective) ?? (perspective === "general");
                  const count = perspectivesData.counts[perspective] || 0;
                  return (
                    <Badge
                      key={perspective}
                      variant={isAllowed ? "default" : "outline"}
                      className={`cursor-pointer transition-colors ${
                        isAllowed ? "" : "hover:bg-primary/10"
                      }`}
                      onClick={() => togglePerspective(perspective)}
                    >
                      <span className="capitalize">{perspective}</span>
                      <span className="ml-1.5 text-xs opacity-70">({count})</span>
                    </Badge>
                  );
                })}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground p-3 bg-muted rounded-lg">
                No summaries with perspective data found.
                New summaries will be tagged with their perspective automatically.
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Click to toggle. Summaries with non-selected perspectives won't be ingested.
            </p>
          </div>

          {/* Current selection summary */}
          {wikiSettings?.wiki_allowed_perspectives && wikiSettings.wiki_allowed_perspectives.length > 0 && (
            <div className="text-sm p-3 bg-primary/5 rounded-lg border border-primary/20">
              <span className="font-medium">Active: </span>
              {wikiSettings.wiki_allowed_perspectives.map((p, i) => (
                <span key={p}>
                  <span className="capitalize">{p}</span>
                  {i < wikiSettings.wiki_allowed_perspectives.length - 1 && ", "}
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Backfill Card */}
      <Card className="border-primary/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Backfill from Summaries
          </CardTitle>
          <CardDescription>
            Process existing summaries into knowledge bases based on settings above.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* What will be populated */}
          <div className="p-3 bg-muted rounded-lg space-y-2">
            <div className="text-sm font-medium">Will populate:</div>
            <div className="flex flex-wrap gap-2">
              {wikiSettings?.wiki_auto_ingest !== false && (
                <Badge variant="default" className="gap-1">
                  <FileText className="h-3 w-3" />
                  Wiki Pages
                </Badge>
              )}
              {wikiSettings?.wiki_ingest_to_vectors && (
                <Badge variant="secondary" className="gap-1">
                  <Cpu className="h-3 w-3" />
                  RuVector
                </Badge>
              )}
              {!wikiSettings?.wiki_auto_ingest && wikiSettings?.wiki_auto_ingest !== undefined && !wikiSettings?.wiki_ingest_to_vectors && (
                <span className="text-sm text-muted-foreground">Nothing enabled - turn on at least one toggle above</span>
              )}
            </div>
          </div>

          {/* Active backfill status */}
          {isBackfillActive && backfillStatus && (
            <div className="space-y-3 p-4 bg-muted rounded-lg">
              <div className="flex items-center justify-between">
                <span className="font-medium flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Backfill in progress
                </span>
                <Badge variant="secondary">{backfillPercent}%</Badge>
              </div>
              <div className="w-full bg-background rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all"
                  style={{ width: `${backfillPercent}%` }}
                />
              </div>
              <div className="text-sm text-muted-foreground">
                {backfillStatus.progress_message || `${backfillStatus.progress_current} / ${backfillStatus.progress_total} summaries`}
              </div>
              {backfillStatus.stats && (
                <div className="flex gap-4 text-xs">
                  <span className="text-green-600">✓ {backfillStatus.stats.ingested} ingested</span>
                  <span className="text-yellow-600">○ {backfillStatus.stats.skipped} skipped</span>
                  <span className="text-red-600">✕ {backfillStatus.stats.failed} failed</span>
                </div>
              )}
              <Button
                variant="destructive"
                size="sm"
                onClick={() => cancelBackfillMutation.mutate()}
                disabled={cancelBackfillMutation.isPending}
              >
                <Square className="h-3 w-3 mr-1" />
                Cancel
              </Button>
            </div>
          )}

          {/* Paused backfill status */}
          {isBackfillPaused && backfillStatus && (
            <div className="space-y-3 p-4 bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
              <div className="flex items-center justify-between">
                <span className="font-medium flex items-center gap-2 text-yellow-800 dark:text-yellow-200">
                  <AlertTriangle className="h-4 w-4" />
                  Backfill paused
                </span>
                <Badge variant="outline" className="border-yellow-500 text-yellow-700 dark:text-yellow-300">{backfillPercent}%</Badge>
              </div>
              <div className="w-full bg-background rounded-full h-2">
                <div
                  className="bg-yellow-500 h-2 rounded-full"
                  style={{ width: `${backfillPercent}%` }}
                />
              </div>
              <div className="text-sm text-yellow-700 dark:text-yellow-300">
                {backfillStatus.progress_message || `${backfillStatus.progress_current} / ${backfillStatus.progress_total} summaries`}
              </div>
              {backfillStatus.stats && (
                <div className="flex gap-4 text-xs">
                  <span className="text-green-600">✓ {backfillStatus.stats.ingested} ingested</span>
                  <span className="text-yellow-600">○ {backfillStatus.stats.skipped} skipped</span>
                  <span className="text-red-600">✕ {backfillStatus.stats.failed} failed</span>
                </div>
              )}
              <p className="text-sm text-yellow-700 dark:text-yellow-300">
                This job was paused (likely due to server restart). Start a new backfill with "Only un-processed summaries" to continue from where it left off.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => cancelBackfillMutation.mutate()}
                disabled={cancelBackfillMutation.isPending}
                className="border-yellow-500 text-yellow-700 hover:bg-yellow-100 dark:text-yellow-300 dark:hover:bg-yellow-900"
              >
                <X className="h-3 w-3 mr-1" />
                Dismiss
              </Button>
            </div>
          )}

          {/* Completed backfill status */}
          {backfillStatus?.status === "completed" && (
            <Alert>
              <Sparkles className="h-4 w-4" />
              <AlertTitle>Backfill Complete</AlertTitle>
              <AlertDescription>
                Processed {backfillStatus.progress_total} summaries.
                {backfillStatus.stats && (
                  <span>
                    {" "}{backfillStatus.stats.ingested} ingested, {backfillStatus.stats.failed} failed.
                  </span>
                )}
              </AlertDescription>
            </Alert>
          )}

          {/* Start backfill controls */}
          {!isBackfillActive && (
            <div className="space-y-3">
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="backfillMode"
                    checked={backfillMode === "unprocessed"}
                    onChange={() => setBackfillMode("unprocessed")}
                    className="w-4 h-4"
                  />
                  <span className="text-sm">Only un-processed summaries</span>
                  <Badge variant="secondary">Recommended</Badge>
                </label>
              </div>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="backfillMode"
                    checked={backfillMode === "all"}
                    onChange={() => setBackfillMode("all")}
                    className="w-4 h-4"
                  />
                  <span className="text-sm">All summaries (full rebuild)</span>
                </label>
              </div>
              <div className="flex items-center gap-4 mb-3">
                <label className="text-sm text-muted-foreground whitespace-nowrap">
                  Min sources to update page:
                </label>
                <select
                  className="w-20 rounded-md border bg-background px-2 py-1 text-sm"
                  value={updateThreshold}
                  onChange={(e) => setUpdateThreshold(Number(e.target.value))}
                >
                  {[1, 2, 3, 5, 10].map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </div>
              <Button
                onClick={() => startBackfillMutation.mutate({ mode: backfillMode, updateThreshold })}
                disabled={startBackfillMutation.isPending || (!wikiSettings?.wiki_auto_ingest && !wikiSettings?.wiki_ingest_to_vectors)}
              >
                {startBackfillMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Start Backfill
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Clear Wiki Card */}
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Clear Wiki
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Delete all wiki pages and sources. This action cannot be undone.
            You can repopulate the wiki afterwards from your summaries.
          </p>

          {!showClearConfirm ? (
            <Button
              variant="destructive"
              onClick={() => setShowClearConfirm(true)}
              disabled={clearMutation.isPending || !stats?.total_pages || isBackfillActive}
            >
              Clear All Wiki Data
            </Button>
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-medium text-destructive">
                Are you sure? This will delete {stats?.total_pages || 0} pages and {stats?.total_sources || 0} sources.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  onClick={() => clearMutation.mutate()}
                  disabled={clearMutation.isPending}
                >
                  {clearMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : null}
                  Yes, Clear Everything
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowClearConfirm(false)}
                  disabled={clearMutation.isPending}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Clear RuVector Card */}
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Clear RuVector
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Delete all RuVector knowledge units, edges, and learning signals.
            This action cannot be undone. Note: There is currently no backfill for RuVector -
            enable "RuVector Knowledge Units" toggle above and regenerate summaries to repopulate.
          </p>

          {!showClearRuVectorConfirm ? (
            <Button
              variant="destructive"
              onClick={() => setShowClearRuVectorConfirm(true)}
              disabled={clearRuVectorMutation.isPending || isBackfillActive}
            >
              Clear All RuVector Data
            </Button>
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-medium text-destructive">
                Are you sure? This will delete all knowledge units and relationships.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  onClick={() => clearRuVectorMutation.mutate()}
                  disabled={clearRuVectorMutation.isPending}
                >
                  {clearRuVectorMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : null}
                  Yes, Clear RuVector
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowClearRuVectorConfirm(false)}
                  disabled={clearRuVectorMutation.isPending}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
