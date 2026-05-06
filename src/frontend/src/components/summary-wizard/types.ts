/**
 * Types for the Unified Summary Wizard (ADR-089)
 */

export type Platform = "discord" | "slack" | "whatsapp";

export type WhenType = "now" | "recurring" | "past";

export type ScheduleFrequency = "daily" | "weekly" | "monthly" | "custom";

export type TimeRange = "4h" | "8h" | "24h" | "48h" | "custom";

export interface WizardState {
  // Step 1: What
  platform: Platform;
  scope: "channel" | "category" | "guild";
  channelIds: string[];
  categoryId: string;

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

  // When: Past options
  dateFrom: Date | null;
  dateTo: Date | null;
  pastGranularity: "single" | "daily";

  // Step 3: Delivery (recurring only)
  destinations: {
    dashboard: boolean;
    discordChannel: boolean;
    discordChannelId: string;
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

  // Past options
  dateFrom: null,
  dateTo: null,
  pastGranularity: "single",

  // Delivery
  destinations: {
    dashboard: true,
    discordChannel: false,
    discordChannelId: "",
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
