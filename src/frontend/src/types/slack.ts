/**
 * Slack integration types (ADR-043)
 */

export type SlackScopeTier = "public" | "full";

export interface SlackWorkspace {
  workspace_id: string;
  workspace_name: string;
  workspace_domain: string | null;
  bot_user_id: string;
  scope_tier: SlackScopeTier;
  is_enterprise: boolean;
  enabled: boolean;
  installed_at: string | null;
  last_sync_at: string | null;
  linked_guild_id: string | null;
}

export interface SlackChannel {
  channel_id: string;
  channel_name: string;
  channel_type: "public" | "private" | "dm" | "mpim";
  is_shared: boolean;
  is_archived: boolean;
  is_sensitive: boolean;
  auto_summarize: boolean;
  member_count: number;
  topic: string | null;
  purpose: string | null;
}

export interface SlackInstallResponse {
  install_url: string;
  scope_tier: string;
  scopes: string[];
}

export interface SlackChannelUpdateRequest {
  auto_summarize?: boolean;
  is_sensitive?: boolean;
  summary_schedule?: string;
}

export interface SlackSyncResponse {
  status: string;
  channels_synced: number;
  users_synced: number;
}

export interface SlackStatusResponse {
  configured: boolean;
  scopes: {
    public: string[];
    full: string[];
  };
}
