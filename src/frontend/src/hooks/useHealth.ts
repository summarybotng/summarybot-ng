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
    queryFn: () => api.get<HealthResponse>("/health"),
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 1,
  });
}
