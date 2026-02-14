import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

// Types
export interface ArchiveSource {
  source_key: string;
  source_type: string;
  server_id: string;
  server_name: string;
  channel_id?: string;
  channel_name?: string;
  summary_count: number;
  date_range?: {
    start: string;
    end: string;
  };
}

export interface GapInfo {
  start_date: string;
  end_date: string;
  days: number;
  type: "missing" | "failed" | "outdated";
}

export interface ScanResult {
  source_key: string;
  total_days: number;
  complete: number;
  failed: number;
  missing: number;
  outdated: number;
  gaps: GapInfo[];
  date_range: {
    start?: string;
    end?: string;
  };
}

export interface CostEstimate {
  periods: number;
  estimated_cost_usd: number;
  estimated_tokens: number;
  model: string;
}

export interface GenerateRequest {
  source_type: string;
  server_id: string;
  channel_ids?: string[];
  date_range: {
    start: string;
    end: string;
  };
  granularity?: string;
  timezone?: string;
  skip_existing?: boolean;
  regenerate_outdated?: boolean;
  regenerate_failed?: boolean;
  max_cost_usd?: number;
  dry_run?: boolean;
  model?: string;
}

export interface GenerationJob {
  job_id: string;
  source_key: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress: {
    total: number;
    completed: number;
    failed: number;
    skipped: number;
  };
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

export interface CostReport {
  total_cost_usd: number;
  total_tokens: number;
  by_source: Record<string, {
    cost_usd: number;
    tokens: number;
    summaries: number;
  }>;
  by_month: Record<string, number>;
}

// Hooks
export function useArchiveSources(sourceType?: string) {
  return useQuery({
    queryKey: ["archive", "sources", sourceType],
    queryFn: async () => {
      const params = sourceType ? `?source_type=${sourceType}` : "";
      return api.get<ArchiveSource[]>(`/archive/sources${params}`);
    },
    staleTime: 30 * 1000, // 30 seconds
  });
}

export function useScanSource(sourceKey: string) {
  return useQuery({
    queryKey: ["archive", "scan", sourceKey],
    queryFn: () => api.get<ScanResult>(`/archive/sources/${encodeURIComponent(sourceKey)}/scan`),
    enabled: !!sourceKey,
    staleTime: 60 * 1000, // 1 minute
  });
}

export function useEstimateCost() {
  return useMutation({
    mutationFn: (request: GenerateRequest) =>
      api.post<CostEstimate>("/archive/estimate", { ...request, dry_run: true }),
  });
}

export function useGenerateArchive() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: GenerateRequest) =>
      api.post<GenerationJob>("/archive/generate", request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive"] });
    },
  });
}

export function useGenerationJob(jobId: string | null) {
  return useQuery({
    queryKey: ["archive", "job", jobId],
    queryFn: () => api.get<GenerationJob>(`/archive/generate/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.status === "running" || data?.status === "pending") {
        return 2000; // Poll every 2 seconds while running
      }
      return false;
    },
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) =>
      api.post(`/archive/generate/${jobId}/cancel`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive"] });
    },
  });
}

export function useCostReport() {
  return useQuery({
    queryKey: ["archive", "costs"],
    queryFn: () => api.get<CostReport>("/archive/costs"),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useImportWhatsApp() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      file,
      groupId,
      groupName,
      format,
    }: {
      file: File;
      groupId: string;
      groupName: string;
      format: "whatsapp_txt" | "reader_bot";
    }) => {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(
        `/api/v1/archive/import/whatsapp?group_id=${encodeURIComponent(groupId)}&group_name=${encodeURIComponent(groupName)}&format=${format}`,
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        throw new Error("Import failed");
      }

      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive", "sources"] });
    },
  });
}
