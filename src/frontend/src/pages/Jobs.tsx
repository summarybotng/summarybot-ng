/**
 * Jobs Page (ADR-040)
 *
 * Top-level page for viewing all background jobs (manual, scheduled, retrospective).
 * Promoted from a tab within Summaries to improve discoverability.
 */

import { motion } from "framer-motion";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { JobsTab } from "@/components/summaries/JobsTab";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock,
  PauseCircle,
  Sparkles,
} from "lucide-react";

interface JobStats {
  running: number;
  pending: number;
  completed_24h: number;
  failed: number;
  paused: number;
}

interface JobsResponse {
  jobs: Array<{
    status: string;
    created_at: string;
  }>;
  total: number;
}

function useJobStats(guildId: string) {
  return useQuery<JobStats>({
    queryKey: ["job-stats", guildId],
    queryFn: async () => {
      // Fetch recent jobs to calculate stats
      const response = await api.get<JobsResponse>(`/guilds/${guildId}/jobs?limit=100`);
      const jobs = response.jobs || [];
      const now = new Date();
      const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);

      return {
        running: jobs.filter((j) => j.status === "running").length,
        pending: jobs.filter((j) => j.status === "pending").length,
        completed_24h: jobs.filter(
          (j) => j.status === "completed" && new Date(j.created_at) > oneDayAgo
        ).length,
        failed: jobs.filter((j) => j.status === "failed").length,
        paused: jobs.filter((j) => j.status === "paused").length,
      };
    },
    refetchInterval: 10000, // Refresh stats every 10 seconds
  });
}

interface StatCardProps {
  title: string;
  count: number;
  icon: React.ElementType;
  variant?: "default" | "success" | "warning" | "destructive";
  isLoading?: boolean;
}

function StatCard({ title, count, icon: Icon, variant = "default", isLoading }: StatCardProps) {
  const variants = {
    default: "bg-muted/30 text-foreground",
    success: "bg-green-500/10 text-green-600 border-green-500/30",
    warning: "bg-amber-500/10 text-amber-600 border-amber-500/30",
    destructive: "bg-red-500/10 text-red-600 border-red-500/30",
  };

  return (
    <Card className={`border ${variants[variant]}`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            {isLoading ? (
              <Loader2 className="h-6 w-6 animate-spin mt-1" />
            ) : (
              <p className="text-2xl font-bold">{count}</p>
            )}
          </div>
          <Icon className="h-8 w-8 opacity-50" />
        </div>
      </CardContent>
    </Card>
  );
}

export function Jobs() {
  const { id } = useParams<{ id: string }>();
  const { data: stats, isLoading: statsLoading } = useJobStats(id || "");

  const hasActiveJobs = (stats?.running || 0) + (stats?.pending || 0) > 0;
  const hasFailedJobs = (stats?.failed || 0) > 0;
  const hasPausedJobs = (stats?.paused || 0) > 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold">Jobs</h1>
          <p className="text-muted-foreground">
            Background tasks and generation status
          </p>
        </div>
        <Button asChild>
          <Link to={`/guilds/${id}/summaries`}>
            <Sparkles className="mr-2 h-4 w-4" />
            Generate Summary
          </Link>
        </Button>
      </motion.div>

      {/* Quick Stats */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-5"
      >
        <StatCard
          title="Running"
          count={stats?.running || 0}
          icon={Loader2}
          variant={hasActiveJobs ? "warning" : "default"}
          isLoading={statsLoading}
        />
        <StatCard
          title="Pending"
          count={stats?.pending || 0}
          icon={Clock}
          isLoading={statsLoading}
        />
        <StatCard
          title="Completed (24h)"
          count={stats?.completed_24h || 0}
          icon={CheckCircle2}
          variant="success"
          isLoading={statsLoading}
        />
        <StatCard
          title="Failed"
          count={stats?.failed || 0}
          icon={AlertCircle}
          variant={hasFailedJobs ? "destructive" : "default"}
          isLoading={statsLoading}
        />
        <StatCard
          title="Paused"
          count={stats?.paused || 0}
          icon={PauseCircle}
          variant={hasPausedJobs ? "warning" : "default"}
          isLoading={statsLoading}
        />
      </motion.div>

      {/* Jobs List */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <JobsTab guildId={id || ""} />
      </motion.div>
    </div>
  );
}
