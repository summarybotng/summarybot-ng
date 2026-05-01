/**
 * React Query hooks for tenant management (ADR-079).
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type {
  Tenant,
  TenantWorkspace,
  TenantMember,
  TenantAdmin,
  TenantBranding,
  DomainVerification,
  CreateTenantRequest,
  UpdateTenantRequest,
  LinkWorkspaceRequest,
  InviteMemberRequest,
  UpdateMemberRequest,
  AddAdminRequest,
  InitiateDomainVerificationRequest,
  UpdateBrandingRequest,
} from "@/types";

const API_BASE = "/api/v1";

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const token = localStorage.getItem("token");
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail?.message || error.message || "Request failed");
  }
  return response.json();
}

// =============================================================================
// Tenant Queries
// =============================================================================

interface TenantsResponse {
  tenants: Tenant[];
}

async function fetchTenants(): Promise<Tenant[]> {
  const response = await fetch(`${API_BASE}/tenants`, {
    headers: getHeaders(),
  });
  const data = await handleResponse<TenantsResponse>(response);
  return data.tenants;
}

export function useTenants() {
  return useQuery({
    queryKey: ["tenants"],
    queryFn: fetchTenants,
    staleTime: 60 * 1000, // 1 minute
  });
}

async function fetchTenant(slug: string): Promise<Tenant> {
  const response = await fetch(`${API_BASE}/tenants/${slug}`, {
    headers: getHeaders(),
  });
  return handleResponse<Tenant>(response);
}

export function useTenantBySlug(slug: string) {
  return useQuery({
    queryKey: ["tenants", slug],
    queryFn: () => fetchTenant(slug),
    enabled: !!slug,
  });
}

// =============================================================================
// Tenant Mutations
// =============================================================================

async function createTenant(data: CreateTenantRequest): Promise<Tenant> {
  const response = await fetch(`${API_BASE}/tenants`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<Tenant>(response);
}

export function useCreateTenant() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createTenant,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tenants"] });
    },
  });
}

async function updateTenant({
  slug,
  data,
}: {
  slug: string;
  data: UpdateTenantRequest;
}): Promise<Tenant> {
  const response = await fetch(`${API_BASE}/tenants/${slug}`, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<Tenant>(response);
}

export function useUpdateTenant() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateTenant,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants"] });
      queryClient.invalidateQueries({ queryKey: ["tenants", slug] });
      queryClient.invalidateQueries({ queryKey: ["currentTenant"] });
    },
  });
}

async function deleteTenant(slug: string): Promise<void> {
  const response = await fetch(`${API_BASE}/tenants/${slug}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail?.message || "Failed to delete tenant");
  }
}

export function useDeleteTenant() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteTenant,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tenants"] });
      queryClient.invalidateQueries({ queryKey: ["currentTenant"] });
    },
  });
}

// =============================================================================
// Workspace Queries
// =============================================================================

async function fetchTenantWorkspaces(slug: string): Promise<TenantWorkspace[]> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/workspaces`, {
    headers: getHeaders(),
  });
  return handleResponse<TenantWorkspace[]>(response);
}

export function useTenantWorkspaces(slug: string) {
  return useQuery({
    queryKey: ["tenants", slug, "workspaces"],
    queryFn: () => fetchTenantWorkspaces(slug),
    enabled: !!slug,
  });
}

// =============================================================================
// Workspace Mutations
// =============================================================================

async function linkWorkspace({
  slug,
  data,
}: {
  slug: string;
  data: LinkWorkspaceRequest;
}): Promise<TenantWorkspace> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/workspaces`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<TenantWorkspace>(response);
}

export function useLinkWorkspace() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: linkWorkspace,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "workspaces"] });
      queryClient.invalidateQueries({ queryKey: ["currentTenant"] });
    },
  });
}

async function unlinkWorkspace({
  slug,
  workspaceId,
}: {
  slug: string;
  workspaceId: string;
}): Promise<void> {
  const response = await fetch(
    `${API_BASE}/tenants/${slug}/workspaces/${workspaceId}`,
    {
      method: "DELETE",
      headers: getHeaders(),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail?.message || "Failed to unlink workspace");
  }
}

export function useUnlinkWorkspace() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: unlinkWorkspace,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "workspaces"] });
      queryClient.invalidateQueries({ queryKey: ["currentTenant"] });
    },
  });
}

// =============================================================================
// Phase 2: Member Management
// =============================================================================

async function fetchTenantMembers(slug: string): Promise<TenantMember[]> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/members`, {
    headers: getHeaders(),
  });
  return handleResponse<TenantMember[]>(response);
}

export function useTenantMembers(slug: string) {
  return useQuery({
    queryKey: ["tenants", slug, "members"],
    queryFn: () => fetchTenantMembers(slug),
    enabled: !!slug,
  });
}

async function inviteMember({
  slug,
  data,
}: {
  slug: string;
  data: InviteMemberRequest;
}): Promise<TenantMember> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/members`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<TenantMember>(response);
}

export function useInviteMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: inviteMember,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "members"] });
    },
  });
}

async function updateMember({
  slug,
  userId,
  data,
}: {
  slug: string;
  userId: string;
  data: UpdateMemberRequest;
}): Promise<TenantMember> {
  const response = await fetch(
    `${API_BASE}/tenants/${slug}/members/${userId}`,
    {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(data),
    }
  );
  return handleResponse<TenantMember>(response);
}

export function useUpdateMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateMember,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "members"] });
    },
  });
}

async function removeMember({
  slug,
  userId,
}: {
  slug: string;
  userId: string;
}): Promise<void> {
  const response = await fetch(
    `${API_BASE}/tenants/${slug}/members/${userId}`,
    {
      method: "DELETE",
      headers: getHeaders(),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail?.message || "Failed to remove member");
  }
}

export function useRemoveMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: removeMember,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "members"] });
    },
  });
}

// =============================================================================
// Phase 2: Admin Management
// =============================================================================

async function fetchTenantAdmins(slug: string): Promise<TenantAdmin[]> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/admins`, {
    headers: getHeaders(),
  });
  return handleResponse<TenantAdmin[]>(response);
}

export function useTenantAdmins(slug: string) {
  return useQuery({
    queryKey: ["tenants", slug, "admins"],
    queryFn: () => fetchTenantAdmins(slug),
    enabled: !!slug,
  });
}

async function addAdmin({
  slug,
  data,
}: {
  slug: string;
  data: AddAdminRequest;
}): Promise<TenantAdmin> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/admins`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<TenantAdmin>(response);
}

export function useAddAdmin() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: addAdmin,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "admins"] });
    },
  });
}

async function removeAdmin({
  slug,
  userId,
}: {
  slug: string;
  userId: string;
}): Promise<void> {
  const response = await fetch(
    `${API_BASE}/tenants/${slug}/admins/${userId}`,
    {
      method: "DELETE",
      headers: getHeaders(),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail?.message || "Failed to remove admin");
  }
}

export function useRemoveAdmin() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: removeAdmin,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "admins"] });
    },
  });
}

// =============================================================================
// Phase 3: Domain Verification
// =============================================================================

async function fetchDomainVerification(slug: string): Promise<DomainVerification> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/domain`, {
    headers: getHeaders(),
  });
  return handleResponse<DomainVerification>(response);
}

export function useDomainVerification(slug: string) {
  return useQuery({
    queryKey: ["tenants", slug, "domain"],
    queryFn: () => fetchDomainVerification(slug),
    enabled: !!slug,
  });
}

async function initiateDomainVerification({
  slug,
  data,
}: {
  slug: string;
  data: InitiateDomainVerificationRequest;
}): Promise<DomainVerification> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/domain`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<DomainVerification>(response);
}

export function useInitiateDomainVerification() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: initiateDomainVerification,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "domain"] });
      queryClient.invalidateQueries({ queryKey: ["tenants", slug] });
    },
  });
}

async function verifyDomain(slug: string): Promise<DomainVerification> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/domain/verify`, {
    method: "POST",
    headers: getHeaders(),
  });
  return handleResponse<DomainVerification>(response);
}

export function useVerifyDomain() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: verifyDomain,
    onSuccess: (_, slug) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "domain"] });
      queryClient.invalidateQueries({ queryKey: ["tenants", slug] });
      queryClient.invalidateQueries({ queryKey: ["currentTenant"] });
    },
  });
}

async function removeDomain(slug: string): Promise<void> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/domain`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail?.message || "Failed to remove domain");
  }
}

export function useRemoveDomain() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: removeDomain,
    onSuccess: (_, slug) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "domain"] });
      queryClient.invalidateQueries({ queryKey: ["tenants", slug] });
      queryClient.invalidateQueries({ queryKey: ["currentTenant"] });
    },
  });
}

// =============================================================================
// Phase 4: Branding
// =============================================================================

async function fetchTenantBranding(slug: string): Promise<TenantBranding> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/branding`, {
    headers: getHeaders(),
  });
  return handleResponse<TenantBranding>(response);
}

export function useTenantBranding(slug: string) {
  return useQuery({
    queryKey: ["tenants", slug, "branding"],
    queryFn: () => fetchTenantBranding(slug),
    enabled: !!slug,
  });
}

async function updateBranding({
  slug,
  data,
}: {
  slug: string;
  data: UpdateBrandingRequest;
}): Promise<TenantBranding> {
  const response = await fetch(`${API_BASE}/tenants/${slug}/branding`, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<TenantBranding>(response);
}

export function useUpdateBranding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateBranding,
    onSuccess: (_, { slug }) => {
      queryClient.invalidateQueries({ queryKey: ["tenants", slug, "branding"] });
      queryClient.invalidateQueries({ queryKey: ["tenants", slug] });
      queryClient.invalidateQueries({ queryKey: ["currentTenant"] });
    },
  });
}
