import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export interface DefaultPrompt {
  name: string;
  category: string;
  description: string;
  content: string;
}

interface DefaultPromptsResponse {
  prompts: DefaultPrompt[];
}

export function useDefaultPrompts() {
  return useQuery({
    queryKey: ["prompts", "defaults"],
    queryFn: async () => {
      const response = await api.get<DefaultPromptsResponse>("/prompts/defaults");
      return response.data.prompts;
    },
    staleTime: 60 * 60 * 1000, // 1 hour - prompts don't change often
  });
}

export function useDefaultPrompt(category: string) {
  return useQuery({
    queryKey: ["prompts", "defaults", category],
    queryFn: async () => {
      const response = await api.get<DefaultPrompt>(`/prompts/defaults/${category}`);
      return response.data;
    },
    staleTime: 60 * 60 * 1000,
    enabled: !!category,
  });
}
