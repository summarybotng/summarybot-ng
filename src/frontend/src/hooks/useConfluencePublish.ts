/**
 * Hooks for Confluence publishing and settings (ADR-099)
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

// ============================================================================
// Publishing Types & Hook
// ============================================================================

export interface PublishToConfluenceRequest {
  force?: boolean;
  timezone?: string;  // ADR-100: User's timezone for footer (e.g., "America/New_York")
}

export interface PublishToConfluenceResponse {
  success: boolean;
  page_id?: string | null;
  page_url?: string | null;
  page_version?: number | null;
  error?: string | null;
  conflict: boolean;
  previously_published: boolean;
}

/**
 * Hook to publish a stored summary to Confluence.
 *
 * ADR-099: Remote Platform Publishing - Confluence MVP.
 * Admin-only operation that creates or updates a Confluence page.
 */
export function useConfluencePublish(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      summaryId,
      request,
    }: {
      summaryId: string;
      request?: PublishToConfluenceRequest;
    }) =>
      api.post<PublishToConfluenceResponse>(
        `/guilds/${guildId}/stored-summaries/${summaryId}/publish-confluence`,
        request || {}
      ),
    onSuccess: (_, { summaryId }) => {
      // Invalidate summary queries to reflect publish status
      queryClient.invalidateQueries({ queryKey: ["stored-summaries", guildId] });
      queryClient.invalidateQueries({
        queryKey: ["stored-summary", guildId, summaryId],
      });
    },
  });
}

// ============================================================================
// Settings Types & Hooks
// ============================================================================

export interface ConfluenceSettingsRequest {
  enabled: boolean;
  base_url: string;
  space_key: string;
  parent_page_id?: string | null;
  email: string;
  api_token?: string | null;  // Only include when updating
  page_title_template?: string;
  // ADR-113: Section toggles
  include_summary?: boolean;
  include_key_points?: boolean;
  include_action_items?: boolean;
  include_participants?: boolean;
  include_labels?: boolean;
  // ADR-114: Page Properties toggles (defaults: participant=off, perspective=on, source=on)
  include_page_properties?: boolean;
  page_properties_in_expander?: boolean;
  prop_show_channel?: boolean;
  prop_show_period_start?: boolean;
  prop_show_period_end?: boolean;
  prop_show_message_count?: boolean;
  prop_show_participant_count?: boolean;  // Default: false
  prop_show_summary_type?: boolean;
  prop_show_perspective?: boolean;  // Default: true
  prop_show_granularity?: boolean;
  prop_show_source?: boolean;  // Default: true
}

export interface ConfluenceSettingsResponse {
  guild_id: string;
  enabled: boolean;
  base_url: string;
  space_key: string;
  parent_page_id?: string | null;
  email: string;
  page_title_template: string;
  configured_by?: string | null;
  configured_at?: string | null;
  updated_at?: string | null;
  is_configured: boolean;
  has_api_token: boolean;
  // ADR-113: Section toggles
  include_summary?: boolean;
  include_key_points?: boolean;
  include_action_items?: boolean;
  include_participants?: boolean;
  include_labels?: boolean;
  // ADR-114: Page Properties toggles
  include_page_properties?: boolean;
  page_properties_in_expander?: boolean;
  prop_show_channel?: boolean;
  prop_show_period_start?: boolean;
  prop_show_period_end?: boolean;
  prop_show_message_count?: boolean;
  prop_show_participant_count?: boolean;
  prop_show_summary_type?: boolean;
  prop_show_perspective?: boolean;
  prop_show_granularity?: boolean;
  prop_show_source?: boolean;
}

export interface ConfluenceTestResponse {
  success: boolean;
  space_name?: string;
  space_key?: string;
  message?: string;
}

/**
 * Hook to fetch Confluence settings for a guild.
 */
export function useConfluenceSettings(guildId: string) {
  return useQuery({
    queryKey: ["confluence-settings", guildId],
    queryFn: () =>
      api.get<ConfluenceSettingsResponse>(
        `/guilds/${guildId}/settings/confluence`
      ),
    enabled: !!guildId,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook to update Confluence settings for a guild.
 */
export function useUpdateConfluenceSettings(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (settings: ConfluenceSettingsRequest) =>
      api.put<ConfluenceSettingsResponse>(
        `/guilds/${guildId}/settings/confluence`,
        settings
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["confluence-settings", guildId],
      });
    },
  });
}

/**
 * Hook to delete Confluence settings for a guild.
 */
export function useDeleteConfluenceSettings(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      api.delete<{ success: boolean; message: string }>(
        `/guilds/${guildId}/settings/confluence`
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["confluence-settings", guildId],
      });
    },
  });
}

/**
 * Hook to test Confluence connection.
 */
export function useTestConfluenceConnection(guildId: string) {
  return useMutation({
    mutationFn: () =>
      api.post<ConfluenceTestResponse>(
        `/guilds/${guildId}/settings/confluence/test`,
        {}
      ),
  });
}
