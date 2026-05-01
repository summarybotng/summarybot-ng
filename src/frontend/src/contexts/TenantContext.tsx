/**
 * Tenant Context for subdomain multi-tenancy (ADR-079).
 * Provides current tenant state and branding configuration.
 */

import { createContext, useContext, useEffect, ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Tenant, TenantWorkspace, CurrentTenantResponse } from "@/types";

const API_BASE = "/api/v1";

interface TenantContextType {
  tenant: Tenant | null;
  workspaces: TenantWorkspace[];
  isLoading: boolean;
  error: Error | null;
  appName: string;
  primaryColor: string | null;
}

const TenantContext = createContext<TenantContextType | undefined>(undefined);

async function fetchCurrentTenant(): Promise<CurrentTenantResponse> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/tenants/current`, { headers });

  if (!response.ok) {
    // 401/403 is expected for unauthenticated users
    if (response.status === 401 || response.status === 403) {
      return { tenant: null, workspaces: [] };
    }
    throw new Error("Failed to fetch current tenant");
  }

  return response.json();
}

export function TenantProvider({ children }: { children: ReactNode }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["currentTenant"],
    queryFn: fetchCurrentTenant,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: false, // Don't retry on 401/403
  });

  const tenant = data?.tenant ?? null;
  const workspaces = data?.workspaces ?? [];

  // Apply branding when tenant changes
  useEffect(() => {
    if (!tenant) {
      // Reset to defaults
      document.documentElement.style.removeProperty("--primary");
      document.title = "SummaryBot";
      // Reset favicon
      const favicon = document.querySelector("link[rel='icon']") as HTMLLinkElement;
      if (favicon) {
        favicon.href = "/favicon.ico";
      }
      return;
    }

    const { branding } = tenant;

    // Apply primary color as CSS variable
    if (branding.primary_color) {
      document.documentElement.style.setProperty("--primary", branding.primary_color);
    }

    // Set document title
    const appName = branding.app_name_override || tenant.name || "SummaryBot";
    document.title = appName;

    // Set favicon
    if (branding.favicon_url) {
      let favicon = document.querySelector("link[rel='icon']") as HTMLLinkElement;
      if (!favicon) {
        favicon = document.createElement("link");
        favicon.rel = "icon";
        document.head.appendChild(favicon);
      }
      favicon.href = branding.favicon_url;
    }

    return () => {
      // Cleanup on unmount
      document.documentElement.style.removeProperty("--primary");
    };
  }, [tenant]);

  const appName = tenant?.branding.app_name_override || tenant?.name || "SummaryBot";
  const primaryColor = tenant?.branding.primary_color ?? null;

  return (
    <TenantContext.Provider
      value={{
        tenant,
        workspaces,
        isLoading,
        error: error as Error | null,
        appName,
        primaryColor,
      }}
    >
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant() {
  const context = useContext(TenantContext);
  if (context === undefined) {
    throw new Error("useTenant must be used within a TenantProvider");
  }
  return context;
}

/**
 * Get whether the current context is within a tenant subdomain.
 */
export function useIsTenantContext() {
  const { tenant } = useTenant();
  return tenant !== null;
}
