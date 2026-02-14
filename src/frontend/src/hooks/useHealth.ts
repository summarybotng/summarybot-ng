import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

interface HealthResponse {
  status: string;
  version?: string;
  build?: string;
  build_date?: string;
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      // Health endpoint is at root level, not under /api/v1
      const response = await fetch("/health");
      if (!response.ok) throw new Error("Health check failed");
      return response.json() as Promise<HealthResponse>;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 1,
  });
}
