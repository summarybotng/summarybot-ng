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
  Clock,
  Calendar,
  Sparkles,
  History,
  Filter,
} from "lucide-react";

interface JobProgress {
  current: number;
  total: number;
  percent: number;
  message: string | null;
}

interface Job {
  job_id: string;
  guild_id: string;
  job_type: "manual" | "scheduled" | "retrospective" | "regenerate";
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "paused";
  scope: string | null;
  schedule_id: string | null;
  progress: JobProgress;
  summary_id: string | null;
  error: string | null;
  pause_reason: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
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
      return { label: "Retrospective", className: "bg-orange-500/10 text-orange-600 border-orange-500/30", icon: History };
    case "regenerate":
      return { label: "Regenerate", className: "bg-green-500/10 text-green-600 border-green-500/30", icon: RefreshCw };
    default:
      return { label: jobType, className: "", icon: null };
  }
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
  isCancelling: boolean;
  isRetrying: boolean;
}

function JobCard({ job, onCancel, onRetry, isCancelling, isRetrying }: JobCardProps) {
  const typeBadge = getJobTypeBadge(job.job_type);
  const statusBadge = getStatusBadge(job.status);
  const TypeIcon = typeBadge.icon;
  const StatusIcon = statusBadge.icon;

  const relativeTime = formatRelativeTime(job.created_at);

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
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-2 flex-wrap">
              {/* Job Type Badge */}
              <Badge variant="outline" className={typeBadge.className}>
                {TypeIcon && <TypeIcon className="mr-1 h-3 w-3" />}
                {typeBadge.label}
              </Badge>
              {/* Status Badge */}
              <Badge variant="outline" className={statusBadge.className}>
                {StatusIcon && <StatusIcon className={`mr-1 h-3 w-3 ${job.status === "running" ? "animate-spin" : ""}`} />}
                {statusBadge.label}
              </Badge>
              {/* Job ID */}
              <span className="text-xs text-muted-foreground font-mono">
                {job.job_id.substring(0, 12)}
              </span>
            </div>
            <span className="text-sm text-muted-foreground">{relativeTime}</span>
          </div>

          {/* Progress bar for running jobs */}
          {(job.status === "running" || job.status === "pending") && (
            <div className="mb-3 space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">{job.progress.message || "Processing..."}</span>
                <span className="font-medium">{Math.round(job.progress.percent)}%</span>
              </div>
              <Progress value={job.progress.percent} className="h-2" />
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

          {/* Details row */}
          <div className="flex items-center gap-4 text-sm text-muted-foreground flex-wrap">
            {job.scope && (
              <div className="flex items-center gap-1">
                <span className="capitalize">{job.scope} scope</span>
              </div>
            )}
            {job.schedule_id && (
              <div className="flex items-center gap-1" title={`Schedule ID: ${job.schedule_id}`}>
                <Clock className="h-3 w-3" />
                <span className="font-mono">{job.schedule_id.substring(0, 8)}</span>
              </div>
            )}
            {job.summary_id && (
              <div className="flex items-center gap-1 text-green-600">
                <CheckCircle2 className="h-3 w-3" />
                <span>Summary created</span>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="mt-3 flex gap-2">
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
          </div>
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
              isCancelling={cancellingJobId === job.job_id}
              isRetrying={retryingJobId === job.job_id}
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
