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
      // api.get returns the JSON data directly, not an axios-style response
      return response.prompts;
    },
    staleTime: 60 * 60 * 1000, // 1 hour - prompts don't change often
  });
}

export function useDefaultPrompt(category: string) {
  return useQuery({
    queryKey: ["prompts", "defaults", category],
    queryFn: async () => {
      // api.get returns the JSON data directly
      const response = await api.get<DefaultPrompt>(`/prompts/defaults/${category}`);
      return response;
    },
    staleTime: 60 * 60 * 1000,
    enabled: !!category,
  });
}
