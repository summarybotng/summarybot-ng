/**
 * Jobs Hooks (ADR-040)
 *
 * Hooks for fetching job data, including active job counts for nav badges.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

interface Job {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "paused";
  created_at: string;
}

interface JobsResponse {
  jobs: Job[];
  total: number;
}

interface ActiveJobCount {
  total: number;
  running: number;
  pending: number;
  failed: number;
  paused: number;
  hasFailedJobs: boolean;
}

/**
 * Hook to get active job counts for navigation badge display.
 * Returns count of running, pending, failed, and paused jobs.
 */
export function useActiveJobCount(guildId: string): {
  data: ActiveJobCount | undefined;
  isLoading: boolean;
} {
  const query = useQuery<ActiveJobCount>({
    queryKey: ["active-job-count", guildId],
    queryFn: async () => {
      // Fetch jobs with active statuses
      const response = await api.get<JobsResponse>(
        `/guilds/${guildId}/jobs?limit=50`
      );
      const jobs = response.jobs || [];

      const running = jobs.filter((j) => j.status === "running").length;
      const pending = jobs.filter((j) => j.status === "pending").length;
      const failed = jobs.filter((j) => j.status === "failed").length;
      const paused = jobs.filter((j) => j.status === "paused").length;

      return {
        total: running + pending + failed + paused,
        running,
        pending,
        failed,
        paused,
        hasFailedJobs: failed > 0,
      };
    },
    enabled: !!guildId,
    refetchInterval: 10000, // Refresh every 10 seconds
    staleTime: 5000, // Consider data fresh for 5 seconds
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
  };
}
