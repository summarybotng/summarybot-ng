import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useToast } from "@/hooks/use-toast";
import {
  BarChart3,
  RefreshCw,
  Loader2,
  Play,
  Pause,
  Square,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Hash,
  Calendar,
  TrendingUp,
  ChevronRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
interface ChannelCoverage {
  channel_id: string;
  channel_name: string | null;
  content_start: string | null;
  content_end: string | null;
  covered_start: string | null;
  covered_end: string | null;
  summary_count: number;
  coverage_percent: number;
  gap_count: number;
  covered_days: number;
  total_days: number;
}

interface CoverageReport {
  guild_id: string;
  platform: string;
  total_coverage_percent: number;
  total_gaps: number;
  total_channels: number;
  covered_channels: number;
  total_summaries: number;
  earliest_content: string | null;
  latest_content: string | null;
  computed_at: string;
  channels: ChannelCoverage[];
}

interface CoverageGap {
  id: string;
  channel_id: string;
  channel_name: string | null;
  gap_start: string;
  gap_end: string;
  gap_days: number;
  status: string;
  priority: number;
  summary_id: string | null;
  error_message: string | null;
}

interface GapsListResponse {
  gaps: CoverageGap[];
  total: number;
}

interface BackfillStatus {
  enabled: boolean;
  paused: boolean;
  priority_mode: string;
  rate_limit: number;
  total_gaps: number;
  completed_gaps: number;
  failed_gaps: number;
  progress_percent: number;
  last_run_at: string | null;
  next_run_at: string | null;
}

interface BackfillRequest {
  channels?: string[];
  priority_mode: string;
  rate_limit: number;
}

// API functions
async function fetchCoverage(guildId: string): Promise<CoverageReport> {
  return api.get<CoverageReport>(`/guilds/${guildId}/coverage`);
}

async function refreshCoverage(guildId: string, includeInventory: boolean): Promise<CoverageReport> {
  return api.post<CoverageReport>(`/guilds/${guildId}/coverage/refresh?include_inventory=${includeInventory}`, {});
}

async function fetchGaps(guildId: string, status?: string): Promise<GapsListResponse> {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  params.append("limit", "100");
  return api.get<GapsListResponse>(`/guilds/${guildId}/coverage/gaps?${params.toString()}`);
}

async function fetchBackfillStatus(guildId: string): Promise<BackfillStatus | null> {
  try {
    return await api.get<BackfillStatus>(`/guilds/${guildId}/coverage/backfill`);
  } catch {
    return null;
  }
}

async function startBackfill(guildId: string, request: BackfillRequest): Promise<BackfillStatus> {
  return api.post<BackfillStatus>(`/guilds/${guildId}/coverage/backfill`, request);
}

async function pauseBackfill(guildId: string): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>(`/guilds/${guildId}/coverage/backfill/pause`, {});
}

async function resumeBackfill(guildId: string): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>(`/guilds/${guildId}/coverage/backfill/resume`, {});
}

async function cancelBackfill(guildId: string): Promise<{ success: boolean }> {
  return api.delete<{ success: boolean }>(`/guilds/${guildId}/coverage/backfill`);
}

// Components
function CoverageOverview({ report }: { report: CoverageReport }) {
  const coverageColor = report.total_coverage_percent >= 80
    ? "text-green-600"
    : report.total_coverage_percent >= 50
    ? "text-yellow-600"
    : "text-red-600";

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <TrendingUp className={`h-5 w-5 ${coverageColor}`} />
            <span className="text-sm text-muted-foreground">Coverage</span>
          </div>
          <div className={`text-3xl font-bold mt-2 ${coverageColor}`}>
            {report.total_coverage_percent.toFixed(1)}%
          </div>
          <Progress value={report.total_coverage_percent} className="mt-2 h-2" />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-orange-500" />
            <span className="text-sm text-muted-foreground">Gaps</span>
          </div>
          <div className="text-3xl font-bold mt-2">{report.total_gaps}</div>
          <p className="text-xs text-muted-foreground mt-1">Periods without summaries</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <Hash className="h-5 w-5 text-blue-500" />
            <span className="text-sm text-muted-foreground">Channels</span>
          </div>
          <div className="text-3xl font-bold mt-2">
            {report.covered_channels}/{report.total_channels}
          </div>
          <p className="text-xs text-muted-foreground mt-1">With summaries</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-purple-500" />
            <span className="text-sm text-muted-foreground">Summaries</span>
          </div>
          <div className="text-3xl font-bold mt-2">{report.total_summaries}</div>
          <p className="text-xs text-muted-foreground mt-1">Total generated</p>
        </CardContent>
      </Card>
    </div>
  );
}

function ChannelCoverageList({ channels, guildId }: { channels: ChannelCoverage[]; guildId: string }) {
  const sortedChannels = [...channels].sort((a, b) => a.coverage_percent - b.coverage_percent);

  return (
    <ScrollArea className="h-[400px]">
      <div className="space-y-2">
        {sortedChannels.map((channel) => {
          const coverageColor = channel.coverage_percent >= 80
            ? "bg-green-500"
            : channel.coverage_percent >= 50
            ? "bg-yellow-500"
            : "bg-red-500";

          return (
            <Link
              key={channel.channel_id}
              to={`/guilds/${guildId}/summaries?channel=${channel.channel_id}`}
              className="flex items-center justify-between p-3 rounded-lg border hover:bg-accent/50 transition-colors cursor-pointer"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <Hash className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  <span className="font-medium truncate">
                    {channel.channel_name || channel.channel_id}
                  </span>
                </div>
                <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                  <span>{channel.summary_count} summaries</span>
                  <span>{channel.covered_days}/{channel.total_days} days</span>
                  {channel.gap_count > 0 && (
                    <span className="text-orange-500">{channel.gap_count} gaps</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3 ml-4">
                <div className="w-24">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span>{channel.coverage_percent.toFixed(0)}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full ${coverageColor} transition-all`}
                      style={{ width: `${channel.coverage_percent}%` }}
                    />
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </div>
            </Link>
          );
        })}
        {channels.length === 0 && (
          <p className="text-center text-muted-foreground py-8">
            No channel coverage data yet. Click "Refresh" to compute coverage.
          </p>
        )}
      </div>
    </ScrollArea>
  );
}

function GapsList({ gaps }: { gaps: CoverageGap[] }) {
  const statusIcons: Record<string, React.ReactNode> = {
    pending: <Clock className="h-4 w-4 text-muted-foreground" />,
    scheduled: <Calendar className="h-4 w-4 text-blue-500" />,
    running: <Loader2 className="h-4 w-4 text-yellow-500 animate-spin" />,
    complete: <CheckCircle2 className="h-4 w-4 text-green-500" />,
    failed: <AlertTriangle className="h-4 w-4 text-red-500" />,
    skipped: <CheckCircle2 className="h-4 w-4 text-muted-foreground" />,
  };

  const statusLabels: Record<string, string> = {
    pending: "Pending",
    scheduled: "Scheduled",
    running: "Running",
    complete: "Complete",
    failed: "Failed",
    skipped: "Skipped",
  };

  return (
    <ScrollArea className="h-[400px]">
      <div className="space-y-2">
        {gaps.map((gap) => (
          <div
            key={gap.id}
            className="flex items-center justify-between p-3 rounded-lg border hover:bg-accent/50 transition-colors"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <Hash className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                <span className="font-medium truncate">
                  {gap.channel_name || gap.channel_id}
                </span>
              </div>
              <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                <span>
                  {new Date(gap.gap_start).toLocaleDateString()} - {new Date(gap.gap_end).toLocaleDateString()}
                </span>
                <span>{gap.gap_days} days</span>
                <Badge variant="outline" className="text-xs">
                  Priority: {gap.priority}
                </Badge>
              </div>
              {gap.error_message && (
                <p className="text-xs text-red-500 mt-1 truncate">{gap.error_message}</p>
              )}
            </div>
            <div className="flex items-center gap-2 ml-4">
              {statusIcons[gap.status]}
              <span className="text-sm">{statusLabels[gap.status]}</span>
            </div>
          </div>
        ))}
        {gaps.length === 0 && (
          <p className="text-center text-muted-foreground py-8">
            No coverage gaps found.
          </p>
        )}
      </div>
    </ScrollArea>
  );
}

function BackfillControls({ guildId }: { guildId: string }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [priorityMode, setPriorityMode] = useState("oldest_first");
  const [rateLimit, setRateLimit] = useState(10);

  const { data: backfillStatus, refetch: refetchBackfill } = useQuery({
    queryKey: ["coverage-backfill", guildId],
    queryFn: () => fetchBackfillStatus(guildId),
    refetchInterval: (query) => {
      const status = query.state.data;
      return status?.enabled && !status?.paused ? 5000 : false;
    },
  });

  const startMutation = useMutation({
    mutationFn: () => startBackfill(guildId, { priority_mode: priorityMode, rate_limit: rateLimit }),
    onSuccess: () => {
      refetchBackfill();
      queryClient.invalidateQueries({ queryKey: ["coverage", guildId] });
      toast({ title: "Backfill started" });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to start backfill", description: error.message, variant: "destructive" });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: () => pauseBackfill(guildId),
    onSuccess: () => {
      refetchBackfill();
      toast({ title: "Backfill paused" });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: () => resumeBackfill(guildId),
    onSuccess: () => {
      refetchBackfill();
      toast({ title: "Backfill resumed" });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelBackfill(guildId),
    onSuccess: () => {
      refetchBackfill();
      toast({ title: "Backfill cancelled" });
    },
  });

  const isActive = backfillStatus?.enabled && !backfillStatus?.paused;
  const isPaused = backfillStatus?.enabled && backfillStatus?.paused;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RefreshCw className="h-5 w-5" />
          Scheduled Backfill
        </CardTitle>
        <CardDescription>
          Automatically fill coverage gaps with historical summaries
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Active backfill status */}
        {backfillStatus?.enabled && (
          <div className="space-y-3 p-4 bg-muted rounded-lg">
            <div className="flex items-center justify-between">
              <span className="font-medium flex items-center gap-2">
                {isActive ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Backfill in progress
                  </>
                ) : (
                  <>
                    <Pause className="h-4 w-4" />
                    Backfill paused
                  </>
                )}
              </span>
              <Badge variant="secondary">{backfillStatus.progress_percent.toFixed(0)}%</Badge>
            </div>
            <Progress value={backfillStatus.progress_percent} className="h-2" />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>
                {backfillStatus.completed_gaps} / {backfillStatus.total_gaps} gaps filled
              </span>
              {backfillStatus.failed_gaps > 0 && (
                <span className="text-red-500">{backfillStatus.failed_gaps} failed</span>
              )}
            </div>
            <div className="flex gap-2">
              {isActive ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => pauseMutation.mutate()}
                  disabled={pauseMutation.isPending}
                >
                  <Pause className="h-4 w-4 mr-1" />
                  Pause
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => resumeMutation.mutate()}
                  disabled={resumeMutation.isPending}
                >
                  <Play className="h-4 w-4 mr-1" />
                  Resume
                </Button>
              )}
              <Button
                variant="destructive"
                size="sm"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
              >
                <Square className="h-4 w-4 mr-1" />
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Start backfill controls */}
        {!backfillStatus?.enabled && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Priority Mode</label>
                <Select value={priorityMode} onValueChange={setPriorityMode}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="oldest_first">Oldest First</SelectItem>
                    <SelectItem value="newest_first">Newest First</SelectItem>
                    <SelectItem value="largest_gaps">Largest Gaps First</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Rate Limit</label>
                <div className="flex items-center gap-3">
                  <Slider
                    value={[rateLimit]}
                    onValueChange={([v]) => setRateLimit(v)}
                    min={1}
                    max={50}
                    step={1}
                    className="flex-1"
                  />
                  <span className="text-sm w-16">{rateLimit}/hr</span>
                </div>
              </div>
            </div>

            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Before starting</AlertTitle>
              <AlertDescription>
                Make sure you've clicked "Refresh Coverage" to compute the latest gaps.
                Backfill will generate summaries for each gap period.
              </AlertDescription>
            </Alert>

            <Button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
              className="w-full"
            >
              {startMutation.isPending ? (
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
  );
}

export function Coverage() {
  const { id: guildId } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [gapFilter, setGapFilter] = useState<string | undefined>(undefined);

  // Fetch coverage report
  const { data: report, isLoading: reportLoading } = useQuery({
    queryKey: ["coverage", guildId],
    queryFn: () => fetchCoverage(guildId!),
    enabled: !!guildId,
  });

  // Fetch gaps
  const { data: gapsData, isLoading: gapsLoading } = useQuery({
    queryKey: ["coverage-gaps", guildId, gapFilter],
    queryFn: () => fetchGaps(guildId!, gapFilter),
    enabled: !!guildId,
  });

  // Refresh mutation
  const refreshMutation = useMutation({
    mutationFn: (includeInventory: boolean) => refreshCoverage(guildId!, includeInventory),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["coverage", guildId] });
      queryClient.invalidateQueries({ queryKey: ["coverage-gaps", guildId] });
      toast({ title: "Coverage refreshed" });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to refresh coverage", description: error.message, variant: "destructive" });
    },
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BarChart3 className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Content Coverage</h1>
            <p className="text-sm text-muted-foreground">
              Track how much of your server's history has been summarized
              {report && (
                <Badge variant="outline" className="ml-2 capitalize">
                  {report.platform}
                </Badge>
              )}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => refreshMutation.mutate(false)}
            disabled={refreshMutation.isPending}
          >
            {refreshMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Refresh
          </Button>
          <Button
            onClick={() => refreshMutation.mutate(true)}
            disabled={refreshMutation.isPending}
          >
            {refreshMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Full Refresh
          </Button>
        </div>
      </div>

      {/* Overview cards */}
      {reportLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      ) : report ? (
        <CoverageOverview report={report} />
      ) : (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>No coverage data</AlertTitle>
          <AlertDescription>
            Click "Full Refresh" to compute coverage from your existing summaries and Discord channel history.
          </AlertDescription>
        </Alert>
      )}

      {/* Time range info */}
      {report && (report.earliest_content || report.latest_content) && (
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Content Range:</span>
              </div>
              <span>
                {report.earliest_content ? new Date(report.earliest_content).toLocaleDateString() : "N/A"}
                {" — "}
                {report.latest_content ? new Date(report.latest_content).toLocaleDateString() : "N/A"}
              </span>
              {report.computed_at && (
                <span className="text-muted-foreground">
                  Last computed: {new Date(report.computed_at).toLocaleString()}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main content tabs */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Tabs defaultValue="channels">
            <TabsList>
              <TabsTrigger value="channels">Channel Coverage</TabsTrigger>
              <TabsTrigger value="gaps">
                Coverage Gaps
                {gapsData && gapsData.total > 0 && (
                  <Badge variant="secondary" className="ml-2">
                    {gapsData.total}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="channels" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Channels</CardTitle>
                  <CardDescription>Coverage breakdown by channel</CardDescription>
                </CardHeader>
                <CardContent>
                  {reportLoading ? (
                    <div className="space-y-2">
                      <Skeleton className="h-16" />
                      <Skeleton className="h-16" />
                      <Skeleton className="h-16" />
                    </div>
                  ) : (
                    <ChannelCoverageList channels={report?.channels || []} guildId={guildId || ""} />
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="gaps" className="mt-4">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Coverage Gaps</CardTitle>
                      <CardDescription>Periods without summaries</CardDescription>
                    </div>
                    <Select value={gapFilter || "all"} onValueChange={(v) => setGapFilter(v === "all" ? undefined : v)}>
                      <SelectTrigger className="w-32">
                        <SelectValue placeholder="Filter" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All</SelectItem>
                        <SelectItem value="pending">Pending</SelectItem>
                        <SelectItem value="scheduled">Scheduled</SelectItem>
                        <SelectItem value="running">Running</SelectItem>
                        <SelectItem value="complete">Complete</SelectItem>
                        <SelectItem value="failed">Failed</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardHeader>
                <CardContent>
                  {gapsLoading ? (
                    <div className="space-y-2">
                      <Skeleton className="h-16" />
                      <Skeleton className="h-16" />
                      <Skeleton className="h-16" />
                    </div>
                  ) : (
                    <GapsList gaps={gapsData?.gaps || []} />
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        {/* Backfill controls sidebar */}
        <div>
          <BackfillControls guildId={guildId!} />
        </div>
      </div>
    </motion.div>
  );
}

export default Coverage;
