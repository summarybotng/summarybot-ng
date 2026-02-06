import type { User, Guild, Channel, Summary, Schedule, Webhook } from "@/types";

export const mockUser: User = {
  id: "123456789012345678",
  username: "DemoUser",
  avatar_url: "https://cdn.discordapp.com/embed/avatars/0.png",
};

export const mockGuilds: Guild[] = [
  {
    id: "111111111111111111",
    name: "Dev Community",
    icon_url: "https://cdn.discordapp.com/embed/avatars/1.png",
    member_count: 1250,
    summary_count: 47,
    last_summary_at: new Date(Date.now() - 3600000).toISOString(),
    config_status: "configured",
  },
  {
    id: "222222222222222222",
    name: "Gaming Squad",
    icon_url: "https://cdn.discordapp.com/embed/avatars/2.png",
    member_count: 89,
    summary_count: 12,
    last_summary_at: new Date(Date.now() - 86400000).toISOString(),
    config_status: "configured",
  },
  {
    id: "333333333333333333",
    name: "Project Alpha",
    icon_url: "https://cdn.discordapp.com/embed/avatars/3.png",
    member_count: 45,
    summary_count: 0,
    last_summary_at: null,
    config_status: "needs_setup",
  },
];

export const mockChannels: Channel[] = [
  {
    id: "444444444444444444",
    name: "general",
    type: "text",
    category: "General",
    enabled: true,
  },
  {
    id: "555555555555555555",
    name: "development",
    type: "text",
    category: "Development",
    enabled: true,
  },
  {
    id: "666666666666666666",
    name: "announcements",
    type: "text",
    category: "General",
    enabled: false,
  },
  {
    id: "777777777777777777",
    name: "gaming-chat",
    type: "text",
    category: "Gaming",
    enabled: true,
  },
];

export const mockSummaries: Summary[] = [
  {
    id: "sum-1",
    channel_id: "444444444444444444",
    channel_name: "general",
    preview: "Team discussed the new feature rollout, bug fixes prioritized for next sprint, and design review scheduled...",
    summary_length: "detailed",
    message_count: 147,
    start_time: new Date(Date.now() - 86400000).toISOString(),
    end_time: new Date().toISOString(),
    created_at: new Date().toISOString(),
  },
  {
    id: "sum-2",
    channel_id: "555555555555555555",
    channel_name: "development",
    preview: "Merged PR #234: Authentication refactor, CI pipeline improvements deployed, new linting rules added...",
    summary_length: "brief",
    message_count: 89,
    start_time: new Date(Date.now() - 86400000).toISOString(),
    end_time: new Date().toISOString(),
    created_at: new Date().toISOString(),
  },
];

export const mockSchedules: Schedule[] = [
  {
    id: "sched-1",
    name: "Daily General Summary",
    channel_ids: ["444444444444444444"],
    schedule_type: "daily",
    schedule_time: "09:00",
    schedule_days: null,
    timezone: "America/New_York",
    is_active: true,
    destinations: [{ type: "discord_channel", target: "444444444444444444", format: "embed" }],
    summary_options: {
      summary_length: "detailed",
      perspective: "developer",
      include_action_items: true,
      include_technical_terms: true,
    },
    last_run: new Date(Date.now() - 86400000).toISOString(),
    next_run: new Date(Date.now() + 86400000).toISOString(),
    run_count: 15,
    failure_count: 0,
  },
  {
    id: "sched-2",
    name: "Weekly Dev Report",
    channel_ids: ["555555555555555555"],
    schedule_type: "weekly",
    schedule_time: "17:00",
    schedule_days: [5],
    timezone: "America/New_York",
    is_active: false,
    destinations: [{ type: "webhook", target: "webhook-1", format: "markdown" }],
    summary_options: {
      summary_length: "comprehensive",
      perspective: "executive",
      include_action_items: true,
      include_technical_terms: false,
    },
    last_run: null,
    next_run: new Date(Date.now() + 259200000).toISOString(),
    run_count: 0,
    failure_count: 0,
  },
];

export const mockWebhooks: Webhook[] = [
  {
    id: "webhook-1",
    name: "Slack Integration",
    url_preview: "https://hooks.slack.com/services/xxx...zzz",
    type: "slack",
    enabled: true,
    last_delivery: new Date(Date.now() - 3600000).toISOString(),
    last_status: "success",
    created_at: new Date(Date.now() - 604800000).toISOString(),
  },
  {
    id: "webhook-2",
    name: "Discord Webhook",
    url_preview: "https://discord.com/api/webhooks/xxx...yyy",
    type: "discord",
    enabled: true,
    last_delivery: new Date(Date.now() - 86400000).toISOString(),
    last_status: "success",
    created_at: new Date(Date.now() - 1209600000).toISOString(),
  },
];

// Generate a mock token
export const mockToken = "mock_token_" + Math.random().toString(36).substring(7);
