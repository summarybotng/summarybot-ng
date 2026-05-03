import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

// ============================================================================
// Types
// ============================================================================

export interface WhatsAppChat {
  chat_id: string;
  chat_name: string;
  import_count: number;
  total_messages: number;
  coverage: {
    earliest: string | null;
    latest: string | null;
  };
}

export interface WhatsAppImportsResponse {
  imports: unknown[];
  total: number;
  chats: WhatsAppChat[];
}

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Fetch WhatsApp chats (imported) for a guild
 *
 * Returns the list of WhatsApp chats that have been imported for this guild,
 * along with message counts and date coverage.
 */
export function useWhatsAppChats(guildId: string) {
  return useQuery({
    queryKey: ["whatsapp", "chats", guildId],
    queryFn: async () => {
      const response = await api.get<WhatsAppImportsResponse>(
        `/whatsapp/guilds/${guildId}/imports`
      );
      return response.chats;
    },
    enabled: !!guildId,
  });
}
