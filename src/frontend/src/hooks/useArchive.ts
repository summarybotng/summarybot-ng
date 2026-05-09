import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

// Types
export interface SourceChannelInfo {
  channel_id: string;
  channel_name: string;
  summary_count: number;
}

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
  guild_id?: string;  // For WhatsApp imports - the Discord guild they belong to
  linked_guilds?: string[];  // For Slack - list of guild IDs with access
  channels?: SourceChannelInfo[];  // For Slack - channel breakdown
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
  // ADR-011: Unified scope selection
  scope?: "channel" | "category" | "guild";
  channel_ids?: string[];
  category_id?: string;
  date_range: {
    start: string;
    end: string;
  };
  granularity?: string;
  timezone?: string;
  skip_existing?: boolean;
  regenerate_outdated?: boolean;
  regenerate_failed?: boolean;
  force_regenerate?: boolean;  // Delete existing and regenerate (ADR-019)
  max_cost_usd?: number;
  dry_run?: boolean;
  model?: string;
  // Summary options
  summary_type?: "brief" | "detailed" | "comprehensive";
  perspective?: "general" | "developer" | "marketing" | "product" | "finance" | "executive" | "support";
}

export interface GenerationJob {
  job_id: string;
  source_key: string;
  status: "pending" | "queued" | "running" | "completed" | "failed" | "cancelled" | "paused";
  progress: {
    total: number;
    completed: number;
    failed: number;
    skipped: number;
  };
  // Job criteria
  date_range?: {
    start: string;
    end: string;
  };
  granularity?: string;
  summary_type?: string;
  perspective?: string;
  server_name?: string;
  // Timestamps
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

export interface SourceCostInfo {
  source_key: string;
  server_name: string;
  total_cost_usd: number;
  summary_count: number;
  current_month: {
    cost_usd: number;
    summaries: number;
    tokens_input: number;
    tokens_output: number;
  };
}

export interface CostReport {
  period: string;
  total_cost_usd: number;
  total_summaries: number;
  sources: SourceCostInfo[];
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
      groupId?: string;  // Optional - derived from filename if not provided
      groupName?: string;  // Optional - derived from filename if not provided
      format?: "whatsapp_txt" | "reader_bot";
    }) => {
      const formData = new FormData();
      formData.append("file", file);

      // Build query params - only include if provided
      const params = new URLSearchParams();
      if (groupId) params.set("group_id", groupId);
      if (groupName) params.set("group_name", groupName);
      params.set("format", format || "whatsapp_txt");

      const response = await fetch(
        `/api/v1/archive/import/whatsapp?${params.toString()}`,
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Import failed");
      }

      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive", "sources"] });
    },
  });
}

// ==================== Sync Types (ADR-007) ====================

export interface SyncStatus {
  enabled: boolean;
  configured: boolean;
  folder_id?: string;
  sync_on_generation: boolean;
  sync_frequency: string;
  create_subfolders: boolean;
  sources_synced: number;
}

export interface SyncResult {
  status: string;
  files_synced: number;
  files_failed: number;
  bytes_uploaded: number;
  errors: string[];
}

export interface DriveStatus {
  connected: boolean;
  provider?: string;
  folder_id?: string;
  quota?: {
    limit: number;
    usage: number;
    usage_in_drive: number;
  };
  error?: string;
}

export interface OAuthConfig {
  configured: boolean;
  client_id_set: boolean;
  redirect_uri: string;
}

export interface ServerSyncConfig {
  server_id: string;
  enabled: boolean;
  folder_id?: string;
  folder_name?: string;
  folder_path?: string;  // ADR-007.1: Full path
  drive_type?: string;  // ADR-007.1: "my_drive" | "shared"
  drive_id?: string;  // ADR-007.1: Shared drive ID
  drive_name?: string;  // ADR-007.1: Drive display name
  user_email?: string;  // ADR-007.1: Connected user's email
  configured_by?: string;
  configured_at?: string;
  last_sync?: string;
  using_fallback: boolean;
}

export interface DriveFolder {
  id: string;
  name: string;
}

// ADR-007.1: Shared drives
export interface SharedDrive {
  id: string;
  name: string;
}

export interface DriveUserInfo {
  email: string;
  name?: string;
  picture?: string;
}

// ==================== Sync Hooks ====================

export function useSyncStatus() {
  return useQuery({
    queryKey: ["archive", "sync", "status"],
    queryFn: () => api.get<SyncStatus>("/archive/sync/status"),
    staleTime: 30 * 1000,
  });
}

export function useDriveStatus() {
  return useQuery({
    queryKey: ["archive", "sync", "drive"],
    queryFn: () => api.get<DriveStatus>("/archive/sync/drive"),
    staleTime: 60 * 1000,
  });
}

export function useOAuthConfig() {
  return useQuery({
    queryKey: ["archive", "oauth", "config"],
    queryFn: () => api.get<OAuthConfig>("/archive/oauth/config"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useServerSyncConfig(serverId: string) {
  return useQuery({
    queryKey: ["archive", "sync", "server", serverId],
    queryFn: () => api.get<ServerSyncConfig>(`/archive/sync/server/${serverId}`),
    enabled: !!serverId,
    staleTime: 30 * 1000,
  });
}

export function useStartOAuth() {
  return useMutation({
    mutationFn: ({ serverId, userId }: { serverId: string; userId: string }) =>
      api.get<{ auth_url: string; state: string }>(
        `/archive/oauth/google?server_id=${serverId}&user_id=${userId}`
      ),
  });
}

export function useDisconnectDrive() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (serverId: string) =>
      api.delete(`/archive/oauth/google/${serverId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive", "sync"] });
    },
  });
}

export function useConfigureServerSync() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      serverId,
      folderId,
      folderName,
      folderPath,
      driveType,
      driveId,
      driveName,
      userId,
    }: {
      serverId: string;
      folderId: string;
      folderName: string;
      folderPath?: string;  // ADR-007.1
      driveType?: string;   // ADR-007.1: "my_drive" | "shared"
      driveId?: string;     // ADR-007.1: For shared drives
      driveName?: string;   // ADR-007.1: Drive display name
      userId?: string;
    }) =>
      api.put(`/archive/sync/server/${serverId}?user_id=${userId || ""}`, {
        folder_id: folderId,
        folder_name: folderName,
        folder_path: folderPath || "",
        drive_type: driveType || "my_drive",
        drive_id: driveId || null,
        drive_name: driveName || (driveType === "my_drive" ? "My Drive" : ""),
        sync_on_generation: true,
        include_metadata: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive", "sync"] });
    },
  });
}

export function useTriggerSync() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sourceKey: string) =>
      api.post<SyncResult>(`/archive/sync/trigger/${encodeURIComponent(sourceKey)}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive", "sync"] });
    },
  });
}

export function useTriggerSyncAll() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post("/archive/sync/trigger"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive", "sync"] });
    },
  });
}

export function useDriveFolders(serverId: string, parentId: string = "root", driveId?: string) {
  return useQuery({
    queryKey: ["archive", "oauth", "folders", serverId, parentId, driveId],
    queryFn: () => {
      let url = `/archive/oauth/google/folders?server_id=${serverId}&parent_id=${parentId}`;
      if (driveId) {
        url += `&drive_id=${driveId}`;
      }
      return api.get<{ parent_id: string; drive_id?: string; folders: DriveFolder[] }>(url);
    },
    enabled: !!serverId,
    staleTime: 60 * 1000,
  });
}

// ADR-007.1: List shared drives
export function useSharedDrives(serverId: string) {
  return useQuery({
    queryKey: ["archive", "oauth", "drives", serverId],
    queryFn: () =>
      api.get<{ drives: SharedDrive[] }>(
        `/archive/oauth/google/drives?server_id=${serverId}`
      ),
    enabled: !!serverId,
    staleTime: 60 * 1000,
  });
}

// ADR-007.1: Get connected user info
export function useDriveUserInfo(serverId: string) {
  return useQuery({
    queryKey: ["archive", "oauth", "user", serverId],
    queryFn: () =>
      api.get<DriveUserInfo>(
        `/archive/oauth/google/user?server_id=${serverId}`
      ),
    enabled: !!serverId,
    staleTime: 5 * 60 * 1000,
  });
}

// ==================== Archive Summaries for Summaries Page ====================

export interface ArchiveGenerationMetadata {
  model?: string;
  prompt_version?: string;
  prompt_checksum?: string;
  tokens_input: number;
  tokens_output: number;
  cost_usd: number;
  duration_seconds?: number;
  has_prompt_data: boolean;
  perspective: string;
}

export interface ArchiveSummary {
  id: string;
  source_key: string;
  date: string;
  channel_name: string;
  summary_text: string;
  message_count: number;
  participant_count: number;
  created_at: string;
  summary_length: string;
  preview: string;
  is_archive: boolean;
  generation?: ArchiveGenerationMetadata;
}

export interface ArchiveSummariesResponse {
  summaries: ArchiveSummary[];
  total: number;
}

export interface ArchiveSummariesOptions {
  limit?: number;
  offset?: number;
  sortBy?: "archive_period" | "message_count" | "created_at";
  sortOrder?: "asc" | "desc";
}

export function useArchiveSummaries(
  serverId: string,
  options: ArchiveSummariesOptions = {}
) {
  const { limit = 50, offset = 0, sortBy = "archive_period", sortOrder = "desc" } = options;

  return useQuery({
    queryKey: ["archive", "summaries", serverId, limit, offset, sortBy, sortOrder],
    queryFn: () =>
      api.get<ArchiveSummariesResponse>(
        `/archive/summaries/${serverId}?limit=${limit}&offset=${offset}&sort_by=${sortBy}&sort_order=${sortOrder}`
      ),
    enabled: !!serverId,
    staleTime: 60 * 1000,
  });
}

export function useArchiveSummary(serverId: string, summaryId: string | null) {
  return useQuery({
    queryKey: ["archive", "summary", serverId, summaryId],
    queryFn: () =>
      api.get<ArchiveSummary & { metadata: Record<string, unknown> }>(
        `/archive/summaries/${serverId}/${summaryId}`
      ),
    enabled: !!serverId && !!summaryId,
    staleTime: 5 * 60 * 1000,
  });
}

// ==================== Jobs Management ====================

export function useAllJobs(status?: string) {
  return useQuery({
    queryKey: ["archive", "jobs", status],
    queryFn: () => {
      const params = status ? `?status=${status}` : "";
      return api.get<GenerationJob[]>(`/archive/jobs${params}`);
    },
    staleTime: 5 * 1000, // 5 seconds - jobs change frequently
    refetchInterval: 10 * 1000, // Poll every 10 seconds
  });
}

export function usePauseJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ jobId, reason }: { jobId: string; reason?: string }) =>
      api.post(`/archive/jobs/${jobId}/pause${reason ? `?reason=${encodeURIComponent(reason)}` : ""}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive", "jobs"] });
      queryClient.invalidateQueries({ queryKey: ["archive", "job"] });
    },
  });
}

export function useResumeJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => api.post(`/archive/jobs/${jobId}/resume`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archive", "jobs"] });
      queryClient.invalidateQueries({ queryKey: ["archive", "job"] });
    },
  });
}
