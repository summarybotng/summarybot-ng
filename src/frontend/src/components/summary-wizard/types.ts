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

  // When: Past options
  dateFrom: Date | null;
  dateTo: Date | null;
  pastGranularity: "single" | "daily" | "weekly";
  pastScheduleDays: number[];  // For weekly: which days to generate (0=Sun, 6=Sat)
  pastLookbackHours: number;   // How many hours to look back for each summary
  forceRegenerate: boolean;    // Delete existing and regenerate
  perChannel: boolean;         // ADR-096: Generate one summary per channel

  // Step 3: Delivery (recurring only)
  destinations: {
    dashboard: boolean;
    discordChannel: boolean;
    discordChannelId: string;
    discordDm: boolean;        // ADR-047: Discord DM delivery
    discordDmUserId: string;   // ADR-047: Discord user ID for DM
    webhook: boolean;
    webhookUrl: string;
    email: boolean;
    emailAddresses: string;
  };

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

  // Past options
  dateFrom: null,
  dateTo: null,
  pastGranularity: "weekly",  // Default to weekly for retrospective
  pastScheduleDays: [6],      // Default to Saturday
  pastLookbackHours: 168,     // Default to 7 days
  forceRegenerate: false,     // Default to skip existing
  perChannel: true,           // ADR-096: Default to per-channel for weekly

  // Delivery
  destinations: {
    dashboard: true,
    discordChannel: false,
    discordChannelId: "",
    discordDm: false,        // ADR-047
    discordDmUserId: "",     // ADR-047
    webhook: false,
    webhookUrl: "",
    email: false,
    emailAddresses: "",
  },

  // Summary options
  summaryLength: "detailed",
  perspective: "general",
  minMessages: 5,
  promptTemplateId: null,
};

export type WizardStep = "what" | "when" | "delivery";

export interface StepProps {
  state: WizardState;
  onChange: (updates: Partial<WizardState>) => void;
  guildId: string;
}
