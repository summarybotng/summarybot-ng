/**
 * Tenant Management Admin UI (ADR-079)
 *
 * Provides:
 * - Create/edit/delete tenants
 * - Link Discord guilds to tenants
 * - Manage members and admins
 * - Custom domain verification
 * - Branding configuration
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useToast } from "@/hooks/use-toast";
import {
  Building2,
  Plus,
  Settings,
  Users,
  Globe,
  Palette,
  Link2,
  Trash2,
  Edit2,
  Check,
  X,
  Loader2,
  Copy,
  ExternalLink,
  Shield,
  Mail,
  ChevronRight,
  AlertTriangle,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/api/client";

// =============================================================================
// Types
// =============================================================================

interface TenantBranding {
  logo_url: string | null;
  primary_color: string | null;
  favicon_url: string | null;
  app_name_override: string | null;
  show_powered_by: boolean;
}

interface Tenant {
  id: string;
  slug: string;
  name: string;
  subdomain: string | null;
  custom_domain: string | null;
  domain_verified: boolean;
  branding: TenantBranding;
  access_mode: string;
  allowed_email_domains: string[];
  created_at: string | null;
  updated_at: string | null;
  created_by: string;
}

interface TenantWorkspace {
  workspace_id: string;
  workspace_type: string;
  display_name: string | null;
  display_order: number;
  added_at: string | null;
  added_by: string;
}

interface TenantMember {
  user_id: string;
  email: string | null;
  access_level: string;
  invited_at: string | null;
  accepted_at: string | null;
}

interface TenantAdmin {
  user_id: string;
  role: string;
  added_at: string | null;
}

interface DomainVerification {
  custom_domain: string | null;
  domain_verified: boolean;
  verification_token: string | null;
  verification_record: string | null;
  cname_target: string | null;
}

interface Guild {
  id: string;
  name: string;
  icon_url: string | null;
}

// =============================================================================
// API Functions
// =============================================================================

async function fetchTenants(): Promise<{ tenants: Tenant[] }> {
  return api.get<{ tenants: Tenant[] }>("/tenants");
}

async function fetchTenant(slug: string): Promise<Tenant> {
  return api.get<Tenant>(`/tenants/${slug}`);
}

async function createTenant(data: {
  slug: string;
  name: string;
  subdomain?: string;
  access_mode?: string;
}): Promise<Tenant> {
  return api.post<Tenant>("/tenants", data);
}

async function updateTenant(
  slug: string,
  data: Partial<{
    name: string;
    subdomain: string;
    custom_domain: string;
    access_mode: string;
    allowed_email_domains: string[];
  }>
): Promise<Tenant> {
  return api.put<Tenant>(`/tenants/${slug}`, data);
}

async function deleteTenant(slug: string): Promise<void> {
  await api.delete(`/tenants/${slug}`);
}

async function fetchWorkspaces(slug: string): Promise<TenantWorkspace[]> {
  return api.get<TenantWorkspace[]>(`/tenants/${slug}/workspaces`);
}

async function linkWorkspace(
  slug: string,
  data: { workspace_id: string; workspace_type: string; display_name?: string }
): Promise<TenantWorkspace> {
  return api.post<TenantWorkspace>(`/tenants/${slug}/workspaces`, data);
}

async function unlinkWorkspace(slug: string, workspaceId: string): Promise<void> {
  await api.delete(`/tenants/${slug}/workspaces/${workspaceId}`);
}

async function fetchMembers(slug: string): Promise<TenantMember[]> {
  return api.get<TenantMember[]>(`/tenants/${slug}/members`);
}

async function inviteMember(
  slug: string,
  data: { email: string; access_level: string }
): Promise<TenantMember> {
  return api.post<TenantMember>(`/tenants/${slug}/members`, data);
}

async function removeMember(slug: string, userId: string): Promise<void> {
  await api.delete(`/tenants/${slug}/members/${userId}`);
}

async function fetchAdmins(slug: string): Promise<TenantAdmin[]> {
  return api.get<TenantAdmin[]>(`/tenants/${slug}/admins`);
}

async function addAdmin(
  slug: string,
  data: { user_id: string; role: string }
): Promise<TenantAdmin> {
  return api.post<TenantAdmin>(`/tenants/${slug}/admins`, data);
}

async function removeAdmin(slug: string, userId: string): Promise<void> {
  await api.delete(`/tenants/${slug}/admins/${userId}`);
}

async function initiateDomainVerification(
  slug: string,
  domain: string
): Promise<DomainVerification> {
  return api.post<DomainVerification>(`/tenants/${slug}/domain/verify`, {
    custom_domain: domain,
  });
}

async function checkDomainVerification(
  slug: string,
  verify: boolean = false
): Promise<DomainVerification> {
  return api.get<DomainVerification>(
    `/tenants/${slug}/domain/status?verify=${verify}`
  );
}

async function updateBranding(
  slug: string,
  data: Partial<TenantBranding>
): Promise<TenantBranding> {
  return api.put<TenantBranding>(`/tenants/${slug}/branding`, data);
}

async function fetchGuilds(): Promise<Guild[]> {
  return api.get<Guild[]>("/guilds");
}

// =============================================================================
// Components
// =============================================================================

function CreateTenantDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (tenant: Tenant) => void;
}) {
  const { toast } = useToast();
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [subdomain, setSubdomain] = useState("");
  const [accessMode, setAccessMode] = useState("authenticated");

  const createMutation = useMutation({
    mutationFn: () =>
      createTenant({
        slug,
        name,
        subdomain: subdomain || undefined,
        access_mode: accessMode,
      }),
    onSuccess: (tenant) => {
      toast({ title: "Tenant created", description: `Created ${tenant.name}` });
      onCreated(tenant);
      onOpenChange(false);
      // Reset form
      setSlug("");
      setName("");
      setSubdomain("");
      setAccessMode("authenticated");
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to create tenant",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Auto-generate slug from name
  const handleNameChange = (value: string) => {
    setName(value);
    if (!slug || slug === name.toLowerCase().replace(/[^a-z0-9]+/g, "-")) {
      setSlug(value.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 32));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Create New Tenant</DialogTitle>
          <DialogDescription>
            Create a new tenant to group workspaces under a custom subdomain.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Name</label>
            <Input
              placeholder="Acme Corporation"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Slug</label>
            <Input
              placeholder="acme-corp"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
            />
            <p className="text-xs text-muted-foreground">
              URL-safe identifier (lowercase, numbers, hyphens)
            </p>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Subdomain</label>
            <div className="flex items-center gap-2">
              <Input
                placeholder="acme"
                value={subdomain}
                onChange={(e) => setSubdomain(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
              />
              <span className="text-sm text-muted-foreground whitespace-nowrap">
                .summarybot.app
              </span>
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Access Mode</label>
            <Select value={accessMode} onValueChange={setAccessMode}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="public">Public (read-only)</SelectItem>
                <SelectItem value="authenticated">Authenticated users</SelectItem>
                <SelectItem value="members_only">Members only</SelectItem>
                <SelectItem value="workspace_members">Workspace members</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={!slug || !name || createMutation.isPending}
          >
            {createMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Create Tenant
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TenantCard({
  tenant,
  onSelect,
}: {
  tenant: Tenant;
  onSelect: () => void;
}) {
  const domainDisplay = tenant.custom_domain && tenant.domain_verified
    ? tenant.custom_domain
    : tenant.subdomain
    ? `${tenant.subdomain}.summarybot.app`
    : null;

  return (
    <Card
      className="cursor-pointer hover:border-primary/50 transition-colors"
      onClick={onSelect}
    >
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <h3 className="font-semibold text-lg">{tenant.name}</h3>
            <p className="text-sm text-muted-foreground">/{tenant.slug}</p>
          </div>
          <ChevronRight className="h-5 w-5 text-muted-foreground" />
        </div>
        <div className="flex flex-wrap gap-2 mt-4">
          {domainDisplay && (
            <Badge variant="outline" className="text-xs">
              <Globe className="h-3 w-3 mr-1" />
              {domainDisplay}
            </Badge>
          )}
          <Badge variant="secondary" className="text-xs capitalize">
            {tenant.access_mode.replace("_", " ")}
          </Badge>
          {tenant.custom_domain && !tenant.domain_verified && (
            <Badge variant="destructive" className="text-xs">
              Domain unverified
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function TenantDetails({
  tenant,
  onBack,
  onDeleted,
}: {
  tenant: Tenant;
  onBack: () => void;
  onDeleted: () => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState("settings");

  // Fetch related data
  const { data: workspaces, refetch: refetchWorkspaces } = useQuery({
    queryKey: ["tenant-workspaces", tenant.slug],
    queryFn: () => fetchWorkspaces(tenant.slug),
  });

  const { data: members, refetch: refetchMembers } = useQuery({
    queryKey: ["tenant-members", tenant.slug],
    queryFn: () => fetchMembers(tenant.slug),
  });

  const { data: admins, refetch: refetchAdmins } = useQuery({
    queryKey: ["tenant-admins", tenant.slug],
    queryFn: () => fetchAdmins(tenant.slug),
  });

  const { data: guilds } = useQuery({
    queryKey: ["guilds"],
    queryFn: fetchGuilds,
  });

  // Delete tenant mutation
  const deleteMutation = useMutation({
    mutationFn: () => deleteTenant(tenant.slug),
    onSuccess: () => {
      toast({ title: "Tenant deleted" });
      queryClient.invalidateQueries({ queryKey: ["tenants"] });
      onDeleted();
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to delete tenant",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={onBack}>
            &larr; Back
          </Button>
          <div>
            <h2 className="text-2xl font-bold">{tenant.name}</h2>
            <p className="text-muted-foreground">/{tenant.slug}</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="settings" className="gap-2">
            <Settings className="h-4 w-4" />
            Settings
          </TabsTrigger>
          <TabsTrigger value="workspaces" className="gap-2">
            <Link2 className="h-4 w-4" />
            Workspaces
            <Badge variant="secondary" className="ml-1">
              {workspaces?.length || 0}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="members" className="gap-2">
            <Users className="h-4 w-4" />
            Members
            <Badge variant="secondary" className="ml-1">
              {members?.length || 0}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="domain" className="gap-2">
            <Globe className="h-4 w-4" />
            Domain
          </TabsTrigger>
          <TabsTrigger value="branding" className="gap-2">
            <Palette className="h-4 w-4" />
            Branding
          </TabsTrigger>
        </TabsList>

        <TabsContent value="settings" className="mt-6">
          <TenantSettingsTab
            tenant={tenant}
            onUpdated={() => queryClient.invalidateQueries({ queryKey: ["tenants"] })}
          />
        </TabsContent>

        <TabsContent value="workspaces" className="mt-6">
          <TenantWorkspacesTab
            tenant={tenant}
            workspaces={workspaces || []}
            guilds={guilds || []}
            onRefresh={refetchWorkspaces}
          />
        </TabsContent>

        <TabsContent value="members" className="mt-6">
          <TenantMembersTab
            tenant={tenant}
            members={members || []}
            admins={admins || []}
            onRefreshMembers={refetchMembers}
            onRefreshAdmins={refetchAdmins}
          />
        </TabsContent>

        <TabsContent value="domain" className="mt-6">
          <TenantDomainTab tenant={tenant} />
        </TabsContent>

        <TabsContent value="branding" className="mt-6">
          <TenantBrandingTab tenant={tenant} />
        </TabsContent>
      </Tabs>

      {/* Danger Zone */}
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="text-destructive flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Danger Zone
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Delete Tenant</p>
              <p className="text-sm text-muted-foreground">
                Permanently delete this tenant and all its data.
              </p>
            </div>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="destructive">Delete Tenant</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete {tenant.name}?</DialogTitle>
                  <DialogDescription>
                    This will permanently delete the tenant, unlink all workspaces,
                    and remove all members. This action cannot be undone.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button variant="outline">Cancel</Button>
                  <Button
                    variant="destructive"
                    onClick={() => deleteMutation.mutate()}
                    disabled={deleteMutation.isPending}
                  >
                    {deleteMutation.isPending && (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    )}
                    Delete Permanently
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TenantSettingsTab({
  tenant,
  onUpdated,
}: {
  tenant: Tenant;
  onUpdated: () => void;
}) {
  const { toast } = useToast();
  const [name, setName] = useState(tenant.name);
  const [subdomain, setSubdomain] = useState(tenant.subdomain || "");
  const [accessMode, setAccessMode] = useState(tenant.access_mode);
  const [emailDomains, setEmailDomains] = useState(
    tenant.allowed_email_domains.join(", ")
  );
  const [hasChanges, setHasChanges] = useState(false);

  const updateMutation = useMutation({
    mutationFn: () =>
      updateTenant(tenant.slug, {
        name,
        subdomain: subdomain || undefined,
        access_mode: accessMode,
        allowed_email_domains: emailDomains
          ? emailDomains.split(",").map((d) => d.trim()).filter(Boolean)
          : [],
      }),
    onSuccess: () => {
      toast({ title: "Settings saved" });
      setHasChanges(false);
      onUpdated();
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to save settings",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>General Settings</CardTitle>
        <CardDescription>
          Configure basic tenant settings and access control.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium">Name</label>
            <Input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setHasChanges(true);
              }}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Subdomain</label>
            <div className="flex items-center gap-2">
              <Input
                value={subdomain}
                onChange={(e) => {
                  setSubdomain(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""));
                  setHasChanges(true);
                }}
              />
              <span className="text-sm text-muted-foreground whitespace-nowrap">
                .summarybot.app
              </span>
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Access Mode</label>
          <Select
            value={accessMode}
            onValueChange={(v) => {
              setAccessMode(v);
              setHasChanges(true);
            }}
          >
            <SelectTrigger className="w-full sm:w-[300px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="public">Public (read-only)</SelectItem>
              <SelectItem value="authenticated">Authenticated users</SelectItem>
              <SelectItem value="members_only">Members only</SelectItem>
              <SelectItem value="workspace_members">Workspace members</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Controls who can access this tenant's dashboards.
          </p>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Allowed Email Domains</label>
          <Input
            placeholder="acme.com, acme.io"
            value={emailDomains}
            onChange={(e) => {
              setEmailDomains(e.target.value);
              setHasChanges(true);
            }}
          />
          <p className="text-xs text-muted-foreground">
            Comma-separated list of email domains. Only users with these domains
            can access (for "authenticated" mode).
          </p>
        </div>

        {hasChanges && (
          <Button
            onClick={() => updateMutation.mutate()}
            disabled={updateMutation.isPending}
          >
            {updateMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Save Changes
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function TenantWorkspacesTab({
  tenant,
  workspaces,
  guilds,
  onRefresh,
}: {
  tenant: Tenant;
  workspaces: TenantWorkspace[];
  guilds: Guild[];
  onRefresh: () => void;
}) {
  const { toast } = useToast();
  const [selectedGuild, setSelectedGuild] = useState("");
  const [displayName, setDisplayName] = useState("");

  // Filter out guilds that are already linked
  const linkedIds = new Set(workspaces.map((w) => w.workspace_id));
  const availableGuilds = guilds.filter((g) => !linkedIds.has(g.id));

  const linkMutation = useMutation({
    mutationFn: () =>
      linkWorkspace(tenant.slug, {
        workspace_id: selectedGuild,
        workspace_type: "discord",
        display_name: displayName || undefined,
      }),
    onSuccess: () => {
      toast({ title: "Workspace linked" });
      setSelectedGuild("");
      setDisplayName("");
      onRefresh();
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to link workspace",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: (workspaceId: string) => unlinkWorkspace(tenant.slug, workspaceId),
    onSuccess: () => {
      toast({ title: "Workspace unlinked" });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to unlink workspace",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  return (
    <div className="space-y-6">
      {/* Link new workspace */}
      <Card>
        <CardHeader>
          <CardTitle>Link Workspace</CardTitle>
          <CardDescription>
            Add a Discord guild to this tenant.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">Discord Guild</label>
              <Select value={selectedGuild} onValueChange={setSelectedGuild}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a guild" />
                </SelectTrigger>
                <SelectContent>
                  {availableGuilds.map((guild) => (
                    <SelectItem key={guild.id} value={guild.id}>
                      {guild.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Display Name (optional)</label>
              <Input
                placeholder="Custom display name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
          </div>
          <Button
            onClick={() => linkMutation.mutate()}
            disabled={!selectedGuild || linkMutation.isPending}
          >
            {linkMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            <Link2 className="mr-2 h-4 w-4" />
            Link Workspace
          </Button>
        </CardContent>
      </Card>

      {/* Linked workspaces list */}
      <Card>
        <CardHeader>
          <CardTitle>Linked Workspaces</CardTitle>
        </CardHeader>
        <CardContent>
          {workspaces.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">
              No workspaces linked yet.
            </p>
          ) : (
            <div className="space-y-2">
              {workspaces.map((workspace) => {
                const guild = guilds.find((g) => g.id === workspace.workspace_id);
                return (
                  <div
                    key={workspace.workspace_id}
                    className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      {guild?.icon_url ? (
                        <img
                          src={guild.icon_url}
                          alt=""
                          className="h-8 w-8 rounded-full"
                        />
                      ) : (
                        <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
                          <Building2 className="h-4 w-4" />
                        </div>
                      )}
                      <div>
                        <p className="font-medium">
                          {workspace.display_name || guild?.name || workspace.workspace_id}
                        </p>
                        <p className="text-xs text-muted-foreground capitalize">
                          {workspace.workspace_type}
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => unlinkMutation.mutate(workspace.workspace_id)}
                      disabled={unlinkMutation.isPending}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TenantMembersTab({
  tenant,
  members,
  admins,
  onRefreshMembers,
  onRefreshAdmins,
}: {
  tenant: Tenant;
  members: TenantMember[];
  admins: TenantAdmin[];
  onRefreshMembers: () => void;
  onRefreshAdmins: () => void;
}) {
  const { toast } = useToast();
  const [email, setEmail] = useState("");
  const [accessLevel, setAccessLevel] = useState("viewer");

  const inviteMutation = useMutation({
    mutationFn: () => inviteMember(tenant.slug, { email, access_level: accessLevel }),
    onSuccess: () => {
      toast({ title: "Member invited" });
      setEmail("");
      onRefreshMembers();
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to invite member",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const removeMemberMutation = useMutation({
    mutationFn: (userId: string) => removeMember(tenant.slug, userId),
    onSuccess: () => {
      toast({ title: "Member removed" });
      onRefreshMembers();
    },
  });

  const removeAdminMutation = useMutation({
    mutationFn: (userId: string) => removeAdmin(tenant.slug, userId),
    onSuccess: () => {
      toast({ title: "Admin removed" });
      onRefreshAdmins();
    },
  });

  return (
    <div className="space-y-6">
      {/* Invite member */}
      <Card>
        <CardHeader>
          <CardTitle>Invite Member</CardTitle>
          <CardDescription>
            Invite someone by email address.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">Email</label>
              <Input
                type="email"
                placeholder="user@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Access Level</label>
              <Select value={accessLevel} onValueChange={setAccessLevel}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="viewer">Viewer (read-only)</SelectItem>
                  <SelectItem value="contributor">Contributor</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button
            onClick={() => inviteMutation.mutate()}
            disabled={!email || inviteMutation.isPending}
          >
            {inviteMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            <Mail className="mr-2 h-4 w-4" />
            Send Invite
          </Button>
        </CardContent>
      </Card>

      {/* Admins */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Administrators
          </CardTitle>
        </CardHeader>
        <CardContent>
          {admins.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">No admins.</p>
          ) : (
            <div className="space-y-2">
              {admins.map((admin) => (
                <div
                  key={admin.user_id}
                  className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                >
                  <div>
                    <p className="font-medium">{admin.user_id}</p>
                    <Badge variant="secondary" className="text-xs capitalize">
                      {admin.role}
                    </Badge>
                  </div>
                  {admin.role !== "owner" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeAdminMutation.mutate(admin.user_id)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Members */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            Members
          </CardTitle>
        </CardHeader>
        <CardContent>
          {members.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">
              No members yet. Invite someone above.
            </p>
          ) : (
            <div className="space-y-2">
              {members.map((member) => (
                <div
                  key={member.user_id}
                  className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                >
                  <div>
                    <p className="font-medium">{member.email || member.user_id}</p>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs capitalize">
                        {member.access_level}
                      </Badge>
                      {!member.accepted_at && (
                        <Badge variant="secondary" className="text-xs">
                          Pending
                        </Badge>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeMemberMutation.mutate(member.user_id)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TenantDomainTab({ tenant }: { tenant: Tenant }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [customDomain, setCustomDomain] = useState(tenant.custom_domain || "");
  const [copied, setCopied] = useState<string | null>(null);

  const { data: verification, refetch } = useQuery({
    queryKey: ["tenant-domain", tenant.slug],
    queryFn: () => checkDomainVerification(tenant.slug),
    enabled: !!tenant.custom_domain,
  });

  const initiateMutation = useMutation({
    mutationFn: () => initiateDomainVerification(tenant.slug, customDomain),
    onSuccess: () => {
      toast({ title: "Verification initiated" });
      refetch();
      queryClient.invalidateQueries({ queryKey: ["tenants"] });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to initiate verification",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const verifyMutation = useMutation({
    mutationFn: () => checkDomainVerification(tenant.slug, true),
    onSuccess: (data) => {
      if (data.domain_verified) {
        toast({ title: "Domain verified!" });
        queryClient.invalidateQueries({ queryKey: ["tenants"] });
      } else {
        toast({
          title: "Verification failed",
          description: "DNS record not found. Please check your DNS settings.",
          variant: "destructive",
        });
      }
      refetch();
    },
  });

  const copyToClipboard = async (text: string, key: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Custom Domain</CardTitle>
        <CardDescription>
          Use your own domain instead of a subdomain.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Current status */}
        {tenant.subdomain && (
          <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg">
            <Globe className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">
              Default: <strong>{tenant.subdomain}.summarybot.app</strong>
            </span>
            <Badge variant="secondary" className="text-xs">Active</Badge>
          </div>
        )}

        {/* Set custom domain */}
        {!tenant.custom_domain && (
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Custom Domain</label>
              <Input
                placeholder="summaries.yourcompany.com"
                value={customDomain}
                onChange={(e) => setCustomDomain(e.target.value)}
              />
            </div>
            <Button
              onClick={() => initiateMutation.mutate()}
              disabled={!customDomain || initiateMutation.isPending}
            >
              {initiateMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Set Custom Domain
            </Button>
          </div>
        )}

        {/* Verification instructions */}
        {tenant.custom_domain && !tenant.domain_verified && verification && (
          <div className="space-y-4">
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Domain Verification Required</AlertTitle>
              <AlertDescription>
                Add these DNS records to verify ownership of {tenant.custom_domain}
              </AlertDescription>
            </Alert>

            <div className="space-y-3">
              <div className="p-3 bg-muted rounded-lg space-y-2">
                <p className="text-sm font-medium">1. TXT Record (Verification)</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs bg-background p-2 rounded">
                    {verification.verification_record}
                  </code>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      copyToClipboard(verification.verification_record || "", "txt")
                    }
                  >
                    {copied === "txt" ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>

              <div className="p-3 bg-muted rounded-lg space-y-2">
                <p className="text-sm font-medium">2. CNAME Record</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs bg-background p-2 rounded">
                    {tenant.custom_domain} CNAME {verification.cname_target}
                  </code>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      copyToClipboard(
                        `${tenant.custom_domain} CNAME ${verification.cname_target}`,
                        "cname"
                      )
                    }
                  >
                    {copied === "cname" ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
            </div>

            <Button
              onClick={() => verifyMutation.mutate()}
              disabled={verifyMutation.isPending}
            >
              {verifyMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              <Check className="mr-2 h-4 w-4" />
              Verify Domain
            </Button>
          </div>
        )}

        {/* Verified */}
        {tenant.custom_domain && tenant.domain_verified && (
          <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
            <Check className="h-4 w-4 text-green-500" />
            <span className="text-sm">
              <strong>{tenant.custom_domain}</strong> is verified and active
            </span>
            <a
              href={`https://${tenant.custom_domain}`}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto"
            >
              <Button variant="ghost" size="sm">
                <ExternalLink className="h-4 w-4" />
              </Button>
            </a>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TenantBrandingTab({ tenant }: { tenant: Tenant }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [logoUrl, setLogoUrl] = useState(tenant.branding.logo_url || "");
  const [primaryColor, setPrimaryColor] = useState(tenant.branding.primary_color || "#000000");
  const [appName, setAppName] = useState(tenant.branding.app_name_override || "");
  const [showPoweredBy, setShowPoweredBy] = useState(tenant.branding.show_powered_by);
  const [hasChanges, setHasChanges] = useState(false);

  const updateMutation = useMutation({
    mutationFn: () =>
      updateBranding(tenant.slug, {
        logo_url: logoUrl || null,
        primary_color: primaryColor || null,
        app_name_override: appName || null,
        show_powered_by: showPoweredBy,
      }),
    onSuccess: () => {
      toast({ title: "Branding saved" });
      setHasChanges(false);
      queryClient.invalidateQueries({ queryKey: ["tenants"] });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to save branding",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Branding</CardTitle>
        <CardDescription>
          Customize the look and feel of your tenant's dashboard.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium">Logo URL</label>
            <Input
              placeholder="https://yourcompany.com/logo.png"
              value={logoUrl}
              onChange={(e) => {
                setLogoUrl(e.target.value);
                setHasChanges(true);
              }}
            />
            {logoUrl && (
              <img
                src={logoUrl}
                alt="Logo preview"
                className="h-12 mt-2"
                onError={(e) => (e.currentTarget.style.display = "none")}
              />
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Primary Color</label>
            <div className="flex gap-2">
              <Input
                type="color"
                value={primaryColor}
                onChange={(e) => {
                  setPrimaryColor(e.target.value);
                  setHasChanges(true);
                }}
                className="w-16 h-10 p-1 cursor-pointer"
              />
              <Input
                value={primaryColor}
                onChange={(e) => {
                  setPrimaryColor(e.target.value);
                  setHasChanges(true);
                }}
                placeholder="#000000"
              />
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">App Name Override</label>
          <Input
            placeholder="Your Company Summaries"
            value={appName}
            onChange={(e) => {
              setAppName(e.target.value);
              setHasChanges(true);
            }}
          />
          <p className="text-xs text-muted-foreground">
            Replaces "SummaryBot" in the header and browser title.
          </p>
        </div>

        <div className="flex items-center justify-between p-4 bg-muted/30 rounded-lg">
          <div>
            <p className="font-medium">Show "Powered by SummaryBot"</p>
            <p className="text-sm text-muted-foreground">
              Display attribution in the footer.
            </p>
          </div>
          <Switch
            checked={showPoweredBy}
            onCheckedChange={(v) => {
              setShowPoweredBy(v);
              setHasChanges(true);
            }}
          />
        </div>

        {hasChanges && (
          <Button
            onClick={() => updateMutation.mutate()}
            disabled={updateMutation.isPending}
          >
            {updateMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Save Branding
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function Tenants() {
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["tenants"],
    queryFn: fetchTenants,
  });

  if (isLoading) {
    return (
      <div className="container mx-auto py-6 space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto py-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Error loading tenants</AlertTitle>
          <AlertDescription>{(error as Error).message}</AlertDescription>
        </Alert>
      </div>
    );
  }

  // If a tenant is selected, show details
  if (selectedTenant) {
    return (
      <div className="container mx-auto py-6">
        <TenantDetails
          tenant={selectedTenant}
          onBack={() => setSelectedTenant(null)}
          onDeleted={() => {
            setSelectedTenant(null);
            queryClient.invalidateQueries({ queryKey: ["tenants"] });
          }}
        />
      </div>
    );
  }

  // Tenant list view
  return (
    <div className="container mx-auto py-6 space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <Building2 className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">Tenants</h1>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Tenant
        </Button>
      </motion.div>

      {data?.tenants.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Building2 className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="font-medium mb-2">No tenants yet</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Create a tenant to group workspaces under a custom subdomain.
            </p>
            <Button onClick={() => setCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Create Your First Tenant
            </Button>
          </CardContent>
        </Card>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {data?.tenants.map((tenant) => (
            <TenantCard
              key={tenant.id}
              tenant={tenant}
              onSelect={() => setSelectedTenant(tenant)}
            />
          ))}
        </motion.div>
      )}

      <CreateTenantDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreated={(tenant) => {
          queryClient.invalidateQueries({ queryKey: ["tenants"] });
          setSelectedTenant(tenant);
        }}
      />
    </div>
  );
}

export default Tenants;
