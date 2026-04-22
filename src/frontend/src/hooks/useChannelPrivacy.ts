/**
 * useChannelPrivacy Hook (ADR-046)
 *
 * Hook for checking channel privacy status and generating warnings
 * when private channels are selected for schedules.
 */

import { useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";

/**
 * Privacy warning returned by the API for a private channel
 */
export interface PrivacyWarning {
  channel_id: string;
  channel_name: string;
  warning: string;
}

/**
 * Response from the privacy check endpoint
 */
interface CheckPrivacyResponse {
  warnings: PrivacyWarning[];
}

/**
 * Hook to check privacy status of selected channels
 *
 * Usage:
 * ```tsx
 * const checkPrivacy = useCheckChannelPrivacy(guildId);
 *
 * // When channels are selected:
 * const result = await checkPrivacy.mutateAsync(selectedChannelIds);
 * if (result.warnings.length > 0) {
 *   // Show privacy warnings
 * }
 * ```
 */
export function useCheckChannelPrivacy(guildId: string) {
  return useMutation({
    mutationFn: async (channelIds: string[]): Promise<CheckPrivacyResponse> => {
      if (!channelIds.length) {
        return { warnings: [] };
      }
      return api.post<CheckPrivacyResponse>(
        `/guilds/${guildId}/check-channel-privacy`,
        { channel_ids: channelIds }
      );
    },
  });
}
