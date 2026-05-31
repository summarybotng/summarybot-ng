/**
 * Jobs Tab Component (ADR-013)
 *
 * Displays all summary generation jobs (manual, scheduled, retrospective)
 * with status, progress, and actions like cancel/retry.
 */

import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatRelativeTime } from "@/contexts/TimezoneContext";
import { api } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import {
  Loader2,
  RefreshCw,
  XCircle,
  CheckCircle2,
  AlertCircle,
  PauseCircle,
  PlayCircle,
  Pause,
  Clock,
  Calendar,
  Sparkles,
  History,
  Filter,
  CalendarRange,
  Layers,
  Server,
  Hash,
  DollarSign,
  BookOpen,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

interface JobProgress {
  current: number;
  total: number;
  percent: number;
  message: string | null;
  current_period?: string | null;
  // ADR-112: Skip reason breakdown
  skipped_exists?: number;
  skipped_locked?: number;
  skipped_no_messages?: number;
  skipped_budget?: number;
}

interface JobDateRange {
  start: string | null;
  end: string | null;
}

interface JobCost {
  cost_usd: number;
  tokens_input: number;
  tokens_output: number;
}

interface Job {
  job_id: string;
  guild_id: string;
  job_type: "manual" | "scheduled" | "retrospective" | "regenerate" | "wiki_backfill";
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "paused";
  scope: string | null;
  schedule_id: string | null;
  schedule_name: string | null;  // ADR-009: For navigation to schedule
  progress: JobProgress;
  summary_id: string | null;
  summary_ids?: string[] | null;
  error: string | null;
  pause_reason: string | null;
  created_at: string;
  started_at: string | null;
  // ADR-112: Job parameters for debugging
  force_regenerate?: boolean;
  skip_existing?: boolean;
  per_channel?: boolean;
  min_channel_messages?: number;
  lookback_hours?: number | null;
  timezone?: string;
  auto_publish_confluence?: boolean;
  completed_at: string | null;
  // Job parameters (ADR-013)
  date_range?: JobDateRange | null;
  granularity?: string | null;
  summary_type?: string;
  perspective?: string;
  channel_ids?: string[];
  category_id?: string | null;
  source_key?: string | null;
  server_name?: string | null;
  cost?: JobCost | null;
}

interface JobsResponse {
  jobs: Job[];
  total: number;
  limit: number;
  offset: number;
}

// Job type badge styling
function getJobTypeBadge(jobType: Job["job_type"]) {
  switch (jobType) {
    case "manual":
      return { label: "Manual", className: "bg-purple-500/10 text-purple-600 border-purple-500/30", icon: Sparkles };
    case "scheduled":
      return { label: "Scheduled", className: "bg-blue-500/10 text-blue-600 border-blue-500/30", icon: Clock };
    case "retrospective":
      return { label: "Retrospective", className: "bg-slate-500/10 text-slate-600 border-slate-500/30", icon: History };
    case "regenerate":
      return { label: "Regenerate", className: "bg-green-500/10 text-green-600 border-green-500/30", icon: RefreshCw };
    case "wiki_backfill":
      return { label: "Wiki Backfill", className: "bg-indigo-500/10 text-indigo-600 border-indigo-500/30", icon: BookOpen };
    default:
      return { label: jobType, className: "", icon: null };
  }
}

// ADR-069: Generate human-readable job title
function generateJobTitle(job: Job): string {
  switch (job.job_type) {
    case "wiki_backfill":
      return "Wiki Knowledge Base Backfill";
    case "manual":
      if (job.server_name) return `${job.server_name} Summary`;
      if (job.scope === "server") return "Server Summary";
      if (job.scope === "category") return "Category Summary";
      return "Manual Summary";
    case "scheduled":
      if (job.granularity === "daily") return "Daily Summary";
      if (job.granularity === "weekly") return "Weekly Summary";
      return "Scheduled Summary";
    case "retrospective":
      return "Retrospective Summary";
    case "regenerate":
      return "Regenerated Summary";
    default:
      return "Summary Job";
  }
}

// ADR-069: Generate job description with key details
function generateJobDescription(job: Job): string {
  const parts: string[] = [];

  // Platform from source_key
  if (job.source_key?.includes("discord")) parts.push("Discord");
  else if (job.source_key?.includes("whatsapp")) parts.push("WhatsApp");
  else if (job.source_key?.includes("telegram")) parts.push("Telegram");

  // Server name
  if (job.server_name && !parts.includes(job.server_name)) {
    parts.push(job.server_name);
  }

  // Scope
  if (job.scope) {
    parts.push(`${job.scope} scope`);
  }

  // Channels
  if (job.channel_ids?.length) {
    parts.push(`${job.channel_ids.length} channel${job.channel_ids.length !== 1 ? "s" : ""}`);
  }

  // Date range
  if (job.date_range?.start && job.date_range?.end) {
    const start = new Date(job.date_range.start).toLocaleDateString();
    const end = new Date(job.date_range.end).toLocaleDateString();
    if (start === end) {
      parts.push(start);
    } else {
      parts.push(`${start} - ${end}`);
    }
  }

  // Granularity for scheduled jobs
  if (job.granularity && job.job_type === "scheduled") {
    parts.push(job.granularity);
  }

  return parts.length > 0 ? parts.join(" · ") : "Processing...";
}

// Status badge styling
function getStatusBadge(status: Job["status"]) {
  switch (status) {
    case "pending":
      return { label: "Pending", className: "bg-yellow-500/10 text-yellow-600 border-yellow-500/30", icon: Clock };
    case "running":
      return { label: "Running", className: "bg-blue-500/10 text-blue-600 border-blue-500/30", icon: Loader2 };
    case "completed":
      return { label: "Completed", className: "bg-green-500/10 text-green-600 border-green-500/30", icon: CheckCircle2 };
    case "failed":
      return { label: "Failed", className: "bg-red-500/10 text-red-600 border-red-500/30", icon: AlertCircle };
    case "cancelled":
      return { label: "Cancelled", className: "bg-gray-500/10 text-gray-600 border-gray-500/30", icon: XCircle };
    case "paused":
      return { label: "Paused", className: "bg-amber-500/10 text-amber-600 border-amber-500/30", icon: PauseCircle };
    default:
      return { label: status, className: "", icon: null };
  }
}

interface JobCardProps {
  job: Job;
  onCancel: () => void;
  onRetry: () => void;
  onPause: () => void;
  onResume: () => void;
  isCancelling: boolean;
  isRetrying: boolean;
  isPausing: boolean;
  isResuming: boolean;
}

function JobCard({ job, onCancel, onRetry, onPause, onResume, isCancelling, isRetrying, isPausing, isResuming }: JobCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const typeBadge = getJobTypeBadge(job.job_type);
  const statusBadge = getStatusBadge(job.status);
  const TypeIcon = typeBadge.icon;
  const StatusIcon = statusBadge.icon;

  const relativeTime = formatRelativeTime(job.created_at);
  const jobTitle = generateJobTitle(job);
  const jobDescription = generateJobDescription(job);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <Card className={`
        border-border/50 transition-all
        ${job.status === "running" ? "border-blue-500/30 bg-blue-500/5" : ""}
        ${job.status === "failed" ? "border-red-500/30 bg-red-500/5" : ""}
        ${job.status === "paused" ? "border-amber-500/30 bg-amber-500/5" : ""}
      `}>
        <CardContent className="p-4">
          {/* ADR-069: Prominent job title and description */}
          <div className="flex items-start gap-3 mb-3">
            {TypeIcon && (
              <div className={`p-2 rounded-lg ${typeBadge.className}`}>
                <TypeIcon className="h-5 w-5" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-medium truncate">{jobTitle}</h3>
                <span className="text-sm text-muted-foreground flex-shrink-0">{relativeTime}</span>
              </div>
              <p className="text-sm text-muted-foreground truncate">{jobDescription}</p>
            </div>
          </div>

          {/* Badges row */}
          <div className="flex items-center gap-2 flex-wrap mb-3">
            {/* Status Badge */}
            <Badge variant="outline" className={statusBadge.className}>
              {StatusIcon && <StatusIcon className={`mr-1 h-3 w-3 ${job.status === "running" ? "animate-spin" : ""}`} />}
              {statusBadge.label}
            </Badge>
            {/* Job Type Badge */}
            <Badge variant="outline" className={typeBadge.className}>
              {typeBadge.label}
            </Badge>
            {/* Job ID */}
            <span className="text-xs text-muted-foreground font-mono">
              {job.job_id.substring(0, 12)}
            </span>
          </div>

          {/* Progress bar for running jobs */}
          {(job.status === "running" || job.status === "pending") && (
            <div className="mb-3 space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">
                  {job.progress.message || "Processing..."}
                  {job.progress.current_period && (
                    <span className="ml-1 text-xs opacity-75">({job.progress.current_period})</span>
                  )}
                </span>
                <span className="font-medium">
                  {job.progress.current}/{job.progress.total} ({Math.round(job.progress.percent)}%)
                </span>
              </div>
              <Progress value={job.progress.percent} className="h-2" />
            </div>
          )}

          {/* Completion message for completed jobs */}
          {job.status === "completed" && job.progress.message && (
            <div className="mb-3 rounded-md bg-green-500/10 border border-green-500/30 p-2">
              <p className="text-sm text-green-700 dark:text-green-400">
                {job.progress.message}
              </p>
            </div>
          )}

          {/* Error message for failed jobs */}
          {job.status === "failed" && job.error && (
            <div className="mb-3 rounded-md bg-red-500/10 border border-red-500/30 p-2">
              <p className="text-sm text-red-600">{job.error}</p>
            </div>
          )}

          {/* Pause reason for paused jobs */}
          {job.status === "paused" && job.pause_reason && (
            <div className="mb-3 rounded-md bg-amber-500/10 border border-amber-500/30 p-2">
              <p className="text-sm text-amber-600">
                Paused: {job.pause_reason === "server_restart" ? "Server restarted while job was running" : job.pause_reason}
              </p>
            </div>
          )}

          {/* Parameters row - ADR-013 */}
          {(job.date_range?.start || job.granularity || job.server_name || job.channel_ids?.length) && (
            <div className="mb-3 rounded-md bg-muted/50 border border-border/50 p-2">
              <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
                {job.date_range?.start && job.date_range?.end && (
                  <div className="flex items-center gap-1" title="Date Range">
                    <CalendarRange className="h-3 w-3" />
                    <span>
                      {new Date(job.date_range.start).toLocaleDateString()} - {new Date(job.date_range.end).toLocaleDateString()}
                    </span>
                  </div>
                )}
                {job.granularity && (
                  <div className="flex items-center gap-1" title="Granularity">
                    <Layers className="h-3 w-3" />
                    <span className="capitalize">{job.granularity}</span>
                  </div>
                )}
                {job.source_key && (
                  <div className="flex items-center gap-1" title="Platform">
                    <Server className="h-3 w-3" />
                    <span className="capitalize">{job.source_key.split(":")[0]}</span>
                  </div>
                )}
                {job.server_name && (
                  <div className="flex items-center gap-1" title="Server">
                    <span>{job.server_name}</span>
                  </div>
                )}
                {job.channel_ids && job.channel_ids.length > 0 && (
                  <div className="flex items-center gap-1" title="Channels">
                    <Hash className="h-3 w-3" />
                    <span>{job.channel_ids.length} channel{job.channel_ids.length !== 1 ? "s" : ""}</span>
                  </div>
                )}
                {job.cost && job.cost.cost_usd > 0 && (
                  <div className="flex items-center gap-1" title={`Tokens: ${job.cost.tokens_input.toLocaleString()} in / ${job.cost.tokens_output.toLocaleString()} out`}>
                    <DollarSign className="h-3 w-3" />
                    <span>${job.cost.cost_usd.toFixed(4)}</span>
                  </div>
                )}
                {/* ADR-112: Job options */}
                {job.force_regenerate && (
                  <Badge variant="outline" className="text-xs bg-orange-500/10 text-orange-600 border-orange-500/30">
                    Force Regen
                  </Badge>
                )}
                {job.skip_existing === false && (
                  <Badge variant="outline" className="text-xs bg-purple-500/10 text-purple-600 border-purple-500/30">
                    No Skip
                  </Badge>
                )}
                {job.per_channel && (
                  <Badge variant="outline" className="text-xs bg-cyan-500/10 text-cyan-600 border-cyan-500/30">
                    Per-Channel
                  </Badge>
                )}
                {job.lookback_hours && (
                  <span className="text-xs" title="Lookback Hours">
                    {job.lookback_hours}h lookback
                  </span>
                )}
                {job.timezone && job.timezone !== "UTC" && (
                  <span className="text-xs" title="Timezone">
                    {job.timezone}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Details row */}
          <div className="flex items-center gap-4 text-sm text-muted-foreground flex-wrap">
            {job.scope && (
              <div className="flex items-center gap-1">
                <span className="capitalize">{job.scope} scope</span>
              </div>
            )}
            {job.schedule_id && (
              <a
                href={`/guilds/${job.guild_id}/schedules?highlight=${job.schedule_id}`}
                className="flex items-center gap-1 text-blue-600 hover:text-blue-700 hover:underline"
                onClick={(e) => e.stopPropagation()}
                title={`Schedule: ${job.schedule_name || job.schedule_id}`}
              >
                <Clock className="h-3 w-3" />
                <span>{job.schedule_name || `Schedule ${job.schedule_id.substring(0, 8)}`}</span>
              </a>
            )}
            {job.summary_id && !job.summary_ids?.length && (
              <a
                href={`/guilds/${job.guild_id}/summaries?view=${job.summary_id}`}
                className="flex items-center gap-1 text-green-600 hover:text-green-700 hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                <CheckCircle2 className="h-3 w-3" />
                <span>View Summary</span>
              </a>
            )}
            {job.summary_ids && job.summary_ids.length > 0 && (
              <a
                href={`/guilds/${job.guild_id}/summaries?source=${job.job_type === "retrospective" ? "archive" : job.job_type}&view=${job.summary_ids[0]}`}
                className="flex items-center gap-1 text-green-600 hover:text-green-700 hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                <CheckCircle2 className="h-3 w-3" />
                <span>
                  {job.summary_ids.length === 1
                    ? "View Summary"
                    : `View ${job.summary_ids.length} Summaries`}
                </span>
              </a>
            )}
          </div>

          {/* Actions */}
          <div className="mt-3 flex gap-2">
            {/* Pause button - only for running jobs */}
            {job.status === "running" && (
              <Button
                variant="outline"
                size="sm"
                onClick={onPause}
                disabled={isPausing}
                className="text-amber-600 hover:text-amber-700"
              >
                {isPausing ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <Pause className="mr-1 h-3 w-3" />
                )}
                Pause
              </Button>
            )}
            {/* Resume button - only for paused jobs */}
            {job.status === "paused" && (
              <Button
                variant="outline"
                size="sm"
                onClick={onResume}
                disabled={isResuming}
                className="text-green-600 hover:text-green-700"
              >
                {isResuming ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <PlayCircle className="mr-1 h-3 w-3" />
                )}
                Resume
              </Button>
            )}
            {/* Cancel button - for running, pending, or paused jobs */}
            {(job.status === "running" || job.status === "pending" || job.status === "paused") && (
              <Button
                variant="outline"
                size="sm"
                onClick={onCancel}
                disabled={isCancelling}
                className="text-red-600 hover:text-red-700"
              >
                {isCancelling ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <XCircle className="mr-1 h-3 w-3" />
                )}
                Cancel
              </Button>
            )}
            {/* Retry button - only for failed jobs */}
            {job.status === "failed" && (
              <Button
                variant="outline"
                size="sm"
                onClick={onRetry}
                disabled={isRetrying}
              >
                {isRetrying ? (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                ) : (
                  <RefreshCw className="mr-1 h-3 w-3" />
                )}
                Retry
              </Button>
            )}
            {/* Expand/collapse details button */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className="ml-auto text-muted-foreground hover:text-foreground"
            >
              {isExpanded ? (
                <>
                  <ChevronUp className="mr-1 h-3 w-3" />
                  Less
                </>
              ) : (
                <>
                  <ChevronDown className="mr-1 h-3 w-3" />
                  Details
                </>
              )}
            </Button>
          </div>

          {/* Expanded details panel */}
          {isExpanded && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-3 rounded-md bg-muted/30 border border-border/50 p-3 overflow-x-auto"
            >
              <h4 className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                Full Job Metadata
              </h4>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <dt className="text-muted-foreground">Job ID</dt>
                <dd className="font-mono">{job.job_id}</dd>

                <dt className="text-muted-foreground">Guild ID</dt>
                <dd className="font-mono">{job.guild_id}</dd>

                <dt className="text-muted-foreground">Job Type</dt>
                <dd>{job.job_type}</dd>

                <dt className="text-muted-foreground">Status</dt>
                <dd>{job.status}</dd>

                <dt className="text-muted-foreground">Scope</dt>
                <dd>{job.scope || "—"}</dd>

                {job.schedule_id && (
                  <>
                    <dt className="text-muted-foreground">Schedule ID</dt>
                    <dd className="font-mono">{job.schedule_id}</dd>
                  </>
                )}

                {job.schedule_name && (
                  <>
                    <dt className="text-muted-foreground">Schedule Name</dt>
                    <dd>{job.schedule_name}</dd>
                  </>
                )}

                <dt className="text-muted-foreground">Created At</dt>
                <dd>{new Date(job.created_at).toLocaleString()}</dd>

                {job.started_at && (
                  <>
                    <dt className="text-muted-foreground">Started At</dt>
                    <dd>{new Date(job.started_at).toLocaleString()}</dd>
                  </>
                )}

                {job.completed_at && (
                  <>
                    <dt className="text-muted-foreground">Completed At</dt>
                    <dd>{new Date(job.completed_at).toLocaleString()}</dd>
                  </>
                )}

                {job.date_range?.start && (
                  <>
                    <dt className="text-muted-foreground">Date Range Start</dt>
                    <dd>{job.date_range.start}</dd>
                  </>
                )}

                {job.date_range?.end && (
                  <>
                    <dt className="text-muted-foreground">Date Range End</dt>
                    <dd>{job.date_range.end}</dd>
                  </>
                )}

                {job.granularity && (
                  <>
                    <dt className="text-muted-foreground">Granularity</dt>
                    <dd>{job.granularity}</dd>
                  </>
                )}

                {job.summary_type && (
                  <>
                    <dt className="text-muted-foreground">Summary Type</dt>
                    <dd>{job.summary_type}</dd>
                  </>
                )}

                {job.perspective && (
                  <>
                    <dt className="text-muted-foreground">Perspective</dt>
                    <dd>{job.perspective}</dd>
                  </>
                )}

                {job.source_key && (
                  <>
                    <dt className="text-muted-foreground">Source Key</dt>
                    <dd className="font-mono">{job.source_key}</dd>
                  </>
                )}

                {job.server_name && (
                  <>
                    <dt className="text-muted-foreground">Server Name</dt>
                    <dd>{job.server_name}</dd>
                  </>
                )}

                {job.category_id && (
                  <>
                    <dt className="text-muted-foreground">Category ID</dt>
                    <dd className="font-mono">{job.category_id}</dd>
                  </>
                )}

                {job.channel_ids && job.channel_ids.length > 0 && (
                  <>
                    <dt className="text-muted-foreground">Channel IDs</dt>
                    <dd className="font-mono break-all">{job.channel_ids.join(", ")}</dd>
                  </>
                )}

                <dt className="text-muted-foreground">Force Regenerate</dt>
                <dd>{job.force_regenerate ? "Yes" : "No"}</dd>

                <dt className="text-muted-foreground">Skip Existing</dt>
                <dd>{job.skip_existing === false ? "No" : "Yes"}</dd>

                <dt className="text-muted-foreground">Per Channel</dt>
                <dd>{job.per_channel ? "Yes" : "No"}</dd>

                {job.min_channel_messages !== undefined && (
                  <>
                    <dt className="text-muted-foreground">Min Channel Messages</dt>
                    <dd>{job.min_channel_messages}</dd>
                  </>
                )}

                {job.lookback_hours && (
                  <>
                    <dt className="text-muted-foreground">Lookback Hours</dt>
                    <dd>{job.lookback_hours}</dd>
                  </>
                )}

                {job.timezone && (
                  <>
                    <dt className="text-muted-foreground">Timezone</dt>
                    <dd>{job.timezone}</dd>
                  </>
                )}

                <dt className="text-muted-foreground">Auto-Publish Confluence</dt>
                <dd>{job.auto_publish_confluence ? "Yes" : "No"}</dd>

                {job.summary_id && (
                  <>
                    <dt className="text-muted-foreground">Summary ID</dt>
                    <dd className="font-mono">{job.summary_id}</dd>
                  </>
                )}

                {job.summary_ids && job.summary_ids.length > 0 && (
                  <>
                    <dt className="text-muted-foreground">Summary IDs ({job.summary_ids.length})</dt>
                    <dd className="font-mono break-all">{job.summary_ids.join(", ")}</dd>
                  </>
                )}

                {job.error && (
                  <>
                    <dt className="text-muted-foreground text-red-500">Error</dt>
                    <dd className="text-red-600 break-all">{job.error}</dd>
                  </>
                )}

                {job.pause_reason && (
                  <>
                    <dt className="text-muted-foreground">Pause Reason</dt>
                    <dd>{job.pause_reason}</dd>
                  </>
                )}

                {job.cost && (
                  <>
                    <dt className="text-muted-foreground">Cost</dt>
                    <dd>${job.cost.cost_usd.toFixed(4)}</dd>

                    <dt className="text-muted-foreground">Tokens In</dt>
                    <dd>{job.cost.tokens_input.toLocaleString()}</dd>

                    <dt className="text-muted-foreground">Tokens Out</dt>
                    <dd>{job.cost.tokens_output.toLocaleString()}</dd>
                  </>
                )}

                <dt className="text-muted-foreground">Progress</dt>
                <dd>
                  {job.progress.current}/{job.progress.total} ({Math.round(job.progress.percent)}%)
                </dd>

                {job.progress.message && (
                  <>
                    <dt className="text-muted-foreground">Progress Message</dt>
                    <dd className="break-all">{job.progress.message}</dd>
                  </>
                )}

                {job.progress.current_period && (
                  <>
                    <dt className="text-muted-foreground">Current Period</dt>
                    <dd>{job.progress.current_period}</dd>
                  </>
                )}

                {/* ADR-112: Skip reason breakdown */}
                {(job.progress.skipped_exists !== undefined && job.progress.skipped_exists > 0) && (
                  <>
                    <dt className="text-muted-foreground">Skipped (Exists)</dt>
                    <dd>{job.progress.skipped_exists}</dd>
                  </>
                )}

                {(job.progress.skipped_locked !== undefined && job.progress.skipped_locked > 0) && (
                  <>
                    <dt className="text-muted-foreground">Skipped (Locked)</dt>
                    <dd>{job.progress.skipped_locked}</dd>
                  </>
                )}

                {(job.progress.skipped_no_messages !== undefined && job.progress.skipped_no_messages > 0) && (
                  <>
                    <dt className="text-muted-foreground">Skipped (No Messages)</dt>
                    <dd>{job.progress.skipped_no_messages}</dd>
                  </>
                )}

                {(job.progress.skipped_budget !== undefined && job.progress.skipped_budget > 0) && (
                  <>
                    <dt className="text-muted-foreground">Skipped (Budget)</dt>
                    <dd>{job.progress.skipped_budget}</dd>
                  </>
                )}
              </dl>
            </motion.div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

interface JobsTabProps {
  guildId: string;
}

export function JobsTab({ guildId }: JobsTabProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [pausingJobId, setPausingJobId] = useState<string | null>(null);
  const [resumingJobId, setResumingJobId] = useState<string | null>(null);

  // Fetch jobs with auto-refresh for active jobs
  const {
    data: jobsData,
    isLoading,
    error,
    refetch,
  } = useQuery<JobsResponse>({
    queryKey: ["jobs", guildId, typeFilter, statusFilter],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("limit", "50");
      if (typeFilter !== "all") params.set("job_type", typeFilter);
      if (statusFilter !== "all") params.set("status", statusFilter);
      return api.get<JobsResponse>(`/guilds/${guildId}/jobs?${params.toString()}`);
    },
    refetchInterval: (query) => {
      // Auto-refresh every 3 seconds if there are active jobs
      const data = query.state.data as JobsResponse | undefined;
      const hasActiveJobs = data?.jobs?.some(
        (j) => j.status === "running" || j.status === "pending"
      );
      return hasActiveJobs ? 3000 : false;
    },
  });

  // Cancel job mutation
  const cancelJob = useMutation({
    mutationFn: async (jobId: string) => {
      setCancellingJobId(jobId);
      const res = await api.post(`/guilds/${guildId}/jobs/${jobId}/cancel`);
      return res.data;
    },
    onSuccess: () => {
      toast({ title: "Job cancelled successfully" });
      queryClient.invalidateQueries({ queryKey: ["jobs", guildId] });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to cancel job",
        description: error?.response?.data?.detail?.message || "An error occurred",
        variant: "destructive",
      });
    },
    onSettled: () => {
      setCancellingJobId(null);
    },
  });

  // Retry job mutation
  const retryJob = useMutation({
    mutationFn: async (jobId: string) => {
      setRetryingJobId(jobId);
      const res = await api.post(`/guilds/${guildId}/jobs/${jobId}/retry`);
      return res.data;
    },
    onSuccess: (data) => {
      toast({
        title: "Retry job created",
        description: `New job ID: ${data.new_job_id?.substring(0, 12)}...`,
      });
      queryClient.invalidateQueries({ queryKey: ["jobs", guildId] });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to retry job",
        description: error?.response?.data?.detail?.message || "An error occurred",
        variant: "destructive",
      });
    },
    onSettled: () => {
      setRetryingJobId(null);
    },
  });

  // Pause job mutation (ADR-068)
  const pauseJob = useMutation({
    mutationFn: async (jobId: string) => {
      setPausingJobId(jobId);
      const res = await api.post(`/guilds/${guildId}/jobs/${jobId}/pause`);
      return res.data;
    },
    onSuccess: () => {
      toast({ title: "Job paused successfully" });
      queryClient.invalidateQueries({ queryKey: ["jobs", guildId] });
      queryClient.invalidateQueries({ queryKey: ["job-stats", guildId] });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to pause job",
        description: error?.response?.data?.detail?.message || "An error occurred",
        variant: "destructive",
      });
    },
    onSettled: () => {
      setPausingJobId(null);
    },
  });

  // Resume job mutation (ADR-068)
  const resumeJob = useMutation({
    mutationFn: async (jobId: string) => {
      setResumingJobId(jobId);
      const res = await api.post(`/guilds/${guildId}/jobs/${jobId}/resume`);
      return res.data;
    },
    onSuccess: () => {
      toast({ title: "Job resumed successfully" });
      queryClient.invalidateQueries({ queryKey: ["jobs", guildId] });
      queryClient.invalidateQueries({ queryKey: ["job-stats", guildId] });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to resume job",
        description: error?.response?.data?.detail?.message || "An error occurred",
        variant: "destructive",
      });
    },
    onSettled: () => {
      setResumingJobId(null);
    },
  });

  const jobs = jobsData?.jobs || [];
  const hasActiveJobs = jobs.some((j) => j.status === "running" || j.status === "pending");

  return (
    <div className="space-y-4">
      {/* Header with filters */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Job Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="manual">Manual</SelectItem>
              <SelectItem value="scheduled">Scheduled</SelectItem>
              <SelectItem value="retrospective">Retrospective</SelectItem>
              <SelectItem value="regenerate">Regenerate</SelectItem>
              <SelectItem value="wiki_backfill">Wiki Backfill</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
              <SelectItem value="paused">Paused</SelectItem>
              <SelectItem value="cancelled">Cancelled</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className={`mr-2 h-4 w-4 ${hasActiveJobs ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Active jobs indicator */}
      {hasActiveJobs && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="rounded-md border border-blue-500/30 bg-blue-500/10 p-3 flex items-center gap-2"
        >
          <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
          <span className="text-sm text-blue-600">
            {jobs.filter((j) => j.status === "running" || j.status === "pending").length} active job(s) - auto-refreshing
          </span>
        </motion.div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Error state */}
      {error && (
        <Card className="border-red-500/30 bg-red-500/10">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-red-600">
              <AlertCircle className="h-5 w-5" />
              <span>Failed to load jobs. Please try again.</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {!isLoading && !error && jobs.length === 0 && (
        <Card>
          <CardContent className="p-8 text-center">
            <Calendar className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <h3 className="font-medium mb-2">No jobs found</h3>
            <p className="text-sm text-muted-foreground">
              {typeFilter !== "all" || statusFilter !== "all"
                ? "No jobs match your filters. Try adjusting the filters."
                : "Jobs will appear here when you generate summaries."}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Jobs list */}
      {!isLoading && !error && jobs.length > 0 && (
        <div className="space-y-3">
          {jobs.map((job) => (
            <JobCard
              key={job.job_id}
              job={job}
              onCancel={() => cancelJob.mutate(job.job_id)}
              onRetry={() => retryJob.mutate(job.job_id)}
              onPause={() => pauseJob.mutate(job.job_id)}
              onResume={() => resumeJob.mutate(job.job_id)}
              isCancelling={cancellingJobId === job.job_id}
              isRetrying={retryingJobId === job.job_id}
              isPausing={pausingJobId === job.job_id}
              isResuming={resumingJobId === job.job_id}
            />
          ))}
        </div>
      )}

      {/* Show total count */}
      {jobsData && jobsData.total > jobs.length && (
        <p className="text-sm text-muted-foreground text-center">
          Showing {jobs.length} of {jobsData.total} jobs
        </p>
      )}
    </div>
  );
}
