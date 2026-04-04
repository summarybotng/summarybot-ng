/**
 * Feed Preview Hook (ADR-037 Phase 4)
 *
 * Fetches formatted feed content for preview display.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { type SummaryFilterCriteria, type ApiCriteria, apiCriteriaToFrontend } from "@/types/filters";

export interface FeedPreviewItem {
  id: string;
  title: string;
  channel_name: string | null;
  created_at: string | null;
  message_count: number;
  preview: string;
  has_action_items: boolean;
  has_key_points: boolean;
  source: string | null;
  perspective: string | null;
  summary_length: string | null;
}

/** Raw API response format (snake_case criteria) */
interface FeedPreviewApiResponse {
  feed_id: string;
  title: string;
  description: string;
  feed_type: string;
  item_count: number;
  last_updated: string | null;
  items: FeedPreviewItem[];
  criteria: ApiCriteria | null;
  has_more: boolean;
}

/** Frontend response format (camelCase criteria) */
export interface FeedPreviewResponse {
  feed_id: string;
  title: string;
  description: string;
  feed_type: string;
  item_count: number;
  last_updated: string | null;
  items: FeedPreviewItem[];
  criteria: SummaryFilterCriteria | null;
  has_more: boolean;
}

interface UseFeedPreviewOptions {
  page?: number;
  limit?: number;
}

export function useFeedPreview(
  guildId: string,
  feedId: string | null,
  options: UseFeedPreviewOptions = {}
) {
  const { page = 1, limit = 10 } = options;

  return useQuery({
    queryKey: ["feed-preview", guildId, feedId, page, limit],
    queryFn: async (): Promise<FeedPreviewResponse> => {
      const response = await api.get<FeedPreviewApiResponse>(
        `/guilds/${guildId}/feeds/${feedId}/preview?page=${page}&limit=${limit}`
      );
      // Convert snake_case criteria to camelCase for frontend components
      return {
        ...response,
        criteria: apiCriteriaToFrontend(response.criteria),
      };
    },
    enabled: !!guildId && !!feedId,
    staleTime: 30000, // 30 seconds
  });
}
