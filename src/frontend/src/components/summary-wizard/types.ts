/**
 * Types for the Unified Summary Wizard (ADR-089)
 */

export type Platform = "discord" | "slack" | "whatsapp";

export type WhenType = "now" | "recurring" | "past";

export type ScheduleFrequency =
  | "fifteen-minutes"
  | "hourly"
  | "every-4-hours"
  | "daily"
  | "weekly"
  | "monthly"
  | "once";

export type TimeRange = "4h" | "8h" | "24h" | "48h" | "custom";

// ADR-094: Split mode for multi-channel summaries
export type SplitMode = "by-channel" | "by-category" | "consolidated";

export interface WizardState {
  // Step 1: What
  platform: Platform;
  scope: "channel" | "category" | "guild";
  channelIds: string[];
  categoryId: string;
  splitMode: SplitMode;  // ADR-094: How to split multi-channel summaries

  // Step 2: When
  whenType: WhenType;

  // When: Now options
  timeRange: TimeRange;
  customHours?: number;

  // When: Recurring options
  frequency: ScheduleFrequency;
  scheduleTime: string;
  scheduleDays: number[];
  timezone: string;
  scheduleName: string;
  enableContinuity: boolean;
  lookbackHours: number;  // How far back to fetch messages (time_range_hours)

  // ADR-101: Rolling period summaries
  rollingPeriod: "none" | "weekly" | "biweekly" | "monthly";
  rollingEndDay: number;  // Day to finalize (0=Mon, 6=Sun)
  accumulationStrategy: "append" | "resummarize" | "hybrid";

  // When: Past options
  dateFrom: Date | null;
  dateTo: Date | null;
  pastGranularity: "single" | "daily" | "weekly";
  pastScheduleDays: number[];  // For weekly: which days to generate (0=Sun, 6=Sat)
  pastLookbackHours: number;   // How many hours to look back for each summary
  forceRegenerate: boolean;    // Delete existing and regenerate
  perChannel: boolean;         // ADR-096: Generate one summary per channel

  // Step 3: Where (delivery destinations)
  destinations: {
    dashboard: boolean;
    discordChannel: boolean;
    discordChannelId: string;
    discordChannelRollingIntermediate: boolean;  // ADR-108: Deliver during rolling period
    discordDm: boolean;        // ADR-047: Discord DM delivery
    discordDmUserId: string;   // ADR-047: Discord user ID for DM
    discordDmRollingIntermediate: boolean;  // ADR-108
    webhook: boolean;
    webhookUrl: string;
    webhookRollingIntermediate: boolean;  // ADR-108
    email: boolean;
    emailAddresses: string;
    emailRollingIntermediate: boolean;  // ADR-108
    confluence: boolean;       // ADR-099: Publish to Confluence
    confluenceRollingIntermediate: boolean;  // ADR-108
  };

  // Page title template (for published destinations)
  pageTitleTemplate: string;   // e.g., "{channels} Summary - {date}"

  // Summary options
  summaryLength: "brief" | "detailed" | "comprehensive";
  perspective: string;
  minMessages: number;
  promptTemplateId: string | null;
}

export const initialWizardState: WizardState = {
  // Step 1
  platform: "discord",
  scope: "channel",
  channelIds: [],
  categoryId: "",
  splitMode: "by-channel",  // ADR-094: Default to split for better focus

  // Step 2
  whenType: "now",

  // Now options
  timeRange: "24h",
  customHours: undefined,

  // Recurring options
  frequency: "daily",
  scheduleTime: "09:00",
  scheduleDays: [],
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Toronto",
  scheduleName: "",
  enableContinuity: false,
  lookbackHours: 24,  // Default: look back 24 hours

  // ADR-101: Rolling period summaries
  rollingPeriod: "none",
  rollingEndDay: 5,  // Default to Saturday (5 = Saturday in 0=Mon system)
  accumulationStrategy: "hybrid",

  // Past options
  dateFrom: null,
  dateTo: null,
  pastGranularity: "weekly",  // Default to weekly for retrospective
  pastScheduleDays: [6],      // Default to Saturday
  pastLookbackHours: 168,     // Default to 7 days
  forceRegenerate: false,     // Default to skip existing
  perChannel: true,           // ADR-096: Default to per-channel for weekly

  // Where (delivery destinations)
  destinations: {
    dashboard: true,
    discordChannel: false,
    discordChannelId: "",
    discordChannelRollingIntermediate: false,  // ADR-108
    discordDm: false,        // ADR-047
    discordDmUserId: "",     // ADR-047
    discordDmRollingIntermediate: false,  // ADR-108
    webhook: false,
    webhookUrl: "",
    webhookRollingIntermediate: false,  // ADR-108
    email: false,
    emailAddresses: "",
    emailRollingIntermediate: false,  // ADR-108
    confluence: false,       // ADR-099
    confluenceRollingIntermediate: false,  // ADR-108
  },

  // Page title template
  pageTitleTemplate: "{channels} Summary - {date}",

  // Summary options
  summaryLength: "detailed",
  perspective: "general",
  minMessages: 5,
  promptTemplateId: null,
};

export type WizardStep = "what" | "when" | "where";

export interface StepProps {
  state: WizardState;
  onChange: (updates: Partial<WizardState>) => void;
  guildId: string;
}

/**
 * Convert a Schedule object to WizardState for editing.
 * This keeps the edit flow in sync with creation.
 */
export function scheduleToWizardState(schedule: {
  id: string;
  name: string;
  scope?: string;
  channel_ids?: string[];
  category_id?: string;
  schedule_type: string;
  schedule_time: string;
  schedule_days?: number[];
  timezone: string;
  platform?: string;
  enable_continuity?: boolean;
  rolling_period?: string;
  rolling_end_day?: number;
  accumulation_strategy?: string;
  time_range_hours?: number;
  prompt_template_id?: string;
  title_template?: string;
  summary_options: {
    summary_length: string;
    perspective: string;
    min_messages?: number;
  };
  destinations: Array<{
    type: string;
    target?: string;
    rolling_deliver_intermediate?: boolean;  // ADR-108
  }>;
}): WizardState {
  // Extract destinations
  const dashboardDest = schedule.destinations.find((d) => d.type === "dashboard");
  const discordChannelDest = schedule.destinations.find((d) => d.type === "discord_channel");
  const discordDmDest = schedule.destinations.find((d) => d.type === "discord_dm");
  const webhookDest = schedule.destinations.find((d) => d.type === "webhook");
  const emailDest = schedule.destinations.find((d) => d.type === "email");
  const confluenceDest = schedule.destinations.find((d) => d.type === "confluence");

  // Map schedule_type to frequency
  const frequencyMap: Record<string, ScheduleFrequency> = {
    "fifteen-minutes": "fifteen-minutes",
    "hourly": "hourly",
    "every-4-hours": "every-4-hours",
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
    "once": "once",
  };

  return {
    // Step 1: What
    platform: (schedule.platform || "discord") as Platform,
    scope: (schedule.scope || "channel") as "channel" | "category" | "guild",
    channelIds: schedule.channel_ids || [],
    categoryId: schedule.category_id || "",
    splitMode: "by-channel",  // Default, not stored in schedule

    // Step 2: When
    whenType: "recurring",  // Edit is always for recurring schedules

    // Now options (not used for edit)
    timeRange: "24h",
    customHours: undefined,

    // Recurring options
    frequency: frequencyMap[schedule.schedule_type] || "daily",
    scheduleTime: schedule.schedule_time,
    scheduleDays: schedule.schedule_days || [],
    timezone: schedule.timezone,
    scheduleName: schedule.name,
    enableContinuity: schedule.enable_continuity ?? false,
    lookbackHours: schedule.time_range_hours || 24,

    // ADR-101: Rolling period
    rollingPeriod: (schedule.rolling_period || "none") as "none" | "weekly" | "biweekly" | "monthly",
    rollingEndDay: schedule.rolling_end_day ?? 5,
    accumulationStrategy: (schedule.accumulation_strategy || "hybrid") as "append" | "resummarize" | "hybrid",

    // Past options (not used for edit)
    dateFrom: null,
    dateTo: null,
    pastGranularity: "weekly",
    pastScheduleDays: [6],
    pastLookbackHours: 168,
    forceRegenerate: false,
    perChannel: true,

    // Step 3: Where
    destinations: {
      dashboard: !!dashboardDest,
      discordChannel: !!discordChannelDest,
      discordChannelId: discordChannelDest?.target || "",
      discordChannelRollingIntermediate: discordChannelDest?.rolling_deliver_intermediate ?? false,  // ADR-108
      discordDm: !!discordDmDest,
      discordDmUserId: discordDmDest?.target || "",
      discordDmRollingIntermediate: discordDmDest?.rolling_deliver_intermediate ?? false,  // ADR-108
      webhook: !!webhookDest,
      webhookUrl: webhookDest?.target || "",
      webhookRollingIntermediate: webhookDest?.rolling_deliver_intermediate ?? false,  // ADR-108
      email: !!emailDest,
      emailAddresses: emailDest?.target || "",
      emailRollingIntermediate: emailDest?.rolling_deliver_intermediate ?? false,  // ADR-108
      confluence: !!confluenceDest,
      confluenceRollingIntermediate: confluenceDest?.rolling_deliver_intermediate ?? false,  // ADR-108
    },

    // Page title template
    pageTitleTemplate: schedule.title_template || "{channels} Summary - {date}",

    // Summary options
    summaryLength: schedule.summary_options.summary_length as "brief" | "detailed" | "comprehensive",
    perspective: schedule.summary_options.perspective,
    minMessages: schedule.summary_options.min_messages ?? 5,
    promptTemplateId: schedule.prompt_template_id || null,
  };
}
