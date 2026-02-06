import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Webhook } from "@/types";

interface WebhooksResponse {
  webhooks: Webhook[];
}

interface WebhookRequest {
  name: string;
  url: string;
  type: "discord" | "slack" | "notion" | "generic";
  enabled: boolean;
}

export function useWebhooks(guildId: string) {
  return useQuery({
    queryKey: ["webhooks", guildId],
    queryFn: () => api.get<WebhooksResponse>(`/guilds/${guildId}/webhooks`),
    select: (data) => data.webhooks,
    enabled: !!guildId,
  });
}

export function useCreateWebhook(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (webhook: WebhookRequest) =>
      api.post<Webhook>(`/guilds/${guildId}/webhooks`, webhook),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhooks", guildId] });
    },
  });
}

export function useUpdateWebhook(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      webhookId,
      webhook,
    }: {
      webhookId: string;
      webhook: Partial<WebhookRequest>;
    }) => api.patch<Webhook>(`/guilds/${guildId}/webhooks/${webhookId}`, webhook),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhooks", guildId] });
    },
  });
}

export function useDeleteWebhook(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (webhookId: string) =>
      api.delete(`/guilds/${guildId}/webhooks/${webhookId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhooks", guildId] });
    },
  });
}

export function useTestWebhook(guildId: string) {
  return useMutation({
    mutationFn: (webhookId: string) =>
      api.post<{ success: boolean; message?: string }>(
        `/guilds/${guildId}/webhooks/${webhookId}/test`
      ),
  });
}
