import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Archive, Hash, Globe, Mail, FileCode, AlertTriangle, MessageCircle, MessageSquare } from "lucide-react";
import type { Schedule, SummaryOptions, Destination, Channel, Category, PromptTemplate } from "@/types";
import { ScopeSelector, type ScopeSelectorValue, type ScopeType } from "@/components/ScopeSelector";
import { useCheckChannelPrivacy, type PrivacyWarning } from "@/hooks/useChannelPrivacy";

const TIMEZONES = [
  "America/Toronto",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Vancouver",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Tokyo",
  "Asia/Singapore",
  "Australia/Sydney",
  "Pacific/Auckland",
  "UTC",
];

// Get user's browser timezone, fallback to America/Toronto
function getBrowserTimezone(): string {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    // If the detected timezone is in our list, use it
    if (TIMEZONES.includes(tz)) {
      return tz;
    }
    // Otherwise default to America/Toronto (Eastern)
    return "America/Toronto";
  } catch {
    return "America/Toronto";
  }
}

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export interface ScheduleFormData {
  name: string;
  // ADR-011: Unified scope selection
  scope: ScopeType;
  channel_ids: string[];
  category_id: string;
  schedule_type: Schedule["schedule_type"];
  schedule_time: string;
  schedule_days: number[];
  timezone: string;
  summary_length: SummaryOptions["summary_length"];
  perspective: SummaryOptions["perspective"];
  min_messages: number;  // Minimum messages required (default 5, set to 1 for low-activity)
  // ADR-034: Guild prompt templates
  prompt_template_id: string | null;
  // ADR-051: Platform selection
  platform: "discord" | "slack";
  // ADR-005: Delivery destinations
  destinations: {
    dashboard: boolean;
    discord_channel: boolean;
    discord_channel_id: string;
    discord_dm: boolean;        // ADR-047: Discord DM delivery
    discord_dm_user_id: string; // ADR-047: Discord user ID for DM
    webhook: boolean;
    webhook_url: string;
    email: boolean;           // ADR-030: Email delivery
    email_addresses: string;  // ADR-030: Comma-separated email addresses
  };
}

interface ScheduleFormProps {
  formData: ScheduleFormData;
  onChange: (data: ScheduleFormData) => void;
  channels?: Channel[];
  categories?: Category[];
  promptTemplates?: PromptTemplate[];  // ADR-034
  guildId?: string;  // ADR-046: For privacy check
}

export function ScheduleForm({ formData, onChange, channels = [], categories = [], promptTemplates = [], guildId = "" }: ScheduleFormProps) {
  const textChannels = channels.filter((c) => c.type === "text");

  // ADR-046: Privacy warnings for private channels
  const [privacyWarnings, setPrivacyWarnings] = useState<PrivacyWarning[]>([]);
  const checkPrivacy = useCheckChannelPrivacy(guildId);

  // Convert form data to ScopeSelector value
  const scopeValue: ScopeSelectorValue = {
    scope: formData.scope,
    channelIds: formData.channel_ids,
    categoryId: formData.category_id,
  };

  const handleScopeChange = (value: ScopeSelectorValue) => {
    onChange({
      ...formData,
      scope: value.scope,
      channel_ids: value.channelIds,
      category_id: value.categoryId,
    });
  };

  // ADR-046: Check privacy when channels are selected
  useEffect(() => {
    if (!guildId || formData.scope !== "channel" || formData.channel_ids.length === 0) {
      setPrivacyWarnings([]);
      return;
    }

    // Debounce the check to avoid too many API calls
    const timeoutId = setTimeout(() => {
      checkPrivacy.mutateAsync(formData.channel_ids).then((result) => {
        setPrivacyWarnings(result.warnings);
      }).catch(() => {
        // Silently fail - privacy check is informational only
        setPrivacyWarnings([]);
      });
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [guildId, formData.scope, formData.channel_ids.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4 py-4">
      <div className="space-y-2">
        <label className="text-sm font-medium">Name</label>
        <Input
          placeholder="Daily morning summary"
          value={formData.name}
          onChange={(e) => onChange({ ...formData, name: e.target.value })}
        />
      </div>

      {/* ADR-051: Platform Selection */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Platform</label>
        <Select
          value={formData.platform}
          onValueChange={(v) => onChange({ ...formData, platform: v as "discord" | "slack" })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="discord">
              <span className="flex items-center gap-2">
                <span className="text-base">🎮</span>
                Discord
              </span>
            </SelectItem>
            <SelectItem value="slack">
              <span className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4" />
                Slack
              </span>
            </SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          {formData.platform === "slack"
            ? "Fetch messages from connected Slack workspace"
            : "Fetch messages from Discord server channels"}
        </p>
      </div>

      {/* ADR-011: Scope Selection */}
      <ScopeSelector
        value={scopeValue}
        onChange={handleScopeChange}
        channels={channels}
        categories={categories}
        compact
      />

      {/* ADR-046: Privacy Warning for Private Channels */}
      {privacyWarnings.length > 0 && (
        <Alert variant="warning">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Privacy Notice</AlertTitle>
          <AlertDescription>
            This schedule includes {privacyWarnings.length} private channel{privacyWarnings.length > 1 ? "s" : ""}.
            Summaries will be visible to all guild members in the dashboard.
            <ul className="mt-2 list-disc list-inside text-sm">
              {privacyWarnings.map((w) => (
                <li key={w.channel_id}>#{w.channel_name}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-2">
        <label className="text-sm font-medium">Schedule Type</label>
        <Select
          value={formData.schedule_type}
          onValueChange={(v) =>
            onChange({ ...formData, schedule_type: v as Schedule["schedule_type"] })
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="fifteen-minutes">Every 15 Minutes</SelectItem>
            <SelectItem value="hourly">Hourly</SelectItem>
            <SelectItem value="every-4-hours">Every 4 Hours</SelectItem>
            <SelectItem value="daily">Daily</SelectItem>
            <SelectItem value="weekly">Weekly</SelectItem>
            <SelectItem value="monthly">Monthly</SelectItem>
            <SelectItem value="once">Once</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {formData.schedule_type === "weekly" && (
        <div className="space-y-2">
          <label className="text-sm font-medium">Days</label>
          <div className="flex flex-wrap gap-2">
            {DAYS.map((day, index) => (
              <Button
                key={day}
                type="button"
                variant={formData.schedule_days.includes(index) ? "default" : "outline"}
                size="sm"
                onClick={() => {
                  const days = formData.schedule_days.includes(index)
                    ? formData.schedule_days.filter((d) => d !== index)
                    : [...formData.schedule_days, index];
                  onChange({ ...formData, schedule_days: days });
                }}
              >
                {day}
              </Button>
            ))}
          </div>
        </div>
      )}

      {/* Hide time picker for interval-based schedules */}
      {!["fifteen-minutes", "hourly", "every-4-hours"].includes(formData.schedule_type) && (
        <div className="space-y-2">
          <label className="text-sm font-medium">Time</label>
          <Input
            type="time"
            value={formData.schedule_time}
            onChange={(e) => onChange({ ...formData, schedule_time: e.target.value })}
          />
        </div>
      )}

      <div className="space-y-2">
        <label className="text-sm font-medium">Timezone</label>
        <Select
          value={formData.timezone}
          onValueChange={(v) => onChange({ ...formData, timezone: v })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIMEZONES.map((tz) => (
              <SelectItem key={tz} value={tz}>
                {tz}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium">Summary Length</label>
        <Select
          value={formData.summary_length}
          onValueChange={(v) =>
            onChange({ ...formData, summary_length: v as SummaryOptions["summary_length"] })
          }
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="brief">Brief</SelectItem>
            <SelectItem value="detailed">Detailed</SelectItem>
            <SelectItem value="comprehensive">Comprehensive</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* ADR-034: Combined Perspective + Custom Templates */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Perspective</label>
        <Select
          value={formData.prompt_template_id ? `template:${formData.prompt_template_id}` : formData.perspective}
          onValueChange={(v) => {
            if (v.startsWith("template:")) {
              // Custom template selected - clear perspective influence
              onChange({ ...formData, prompt_template_id: v.replace("template:", ""), perspective: "general" });
            } else {
              // Built-in perspective selected - clear template
              onChange({ ...formData, perspective: v as SummaryOptions["perspective"], prompt_template_id: null });
            }
          }}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="general">General</SelectItem>
            <SelectItem value="developer">Developer</SelectItem>
            <SelectItem value="marketing">Marketing</SelectItem>
            <SelectItem value="executive">Executive</SelectItem>
            <SelectItem value="support">Support</SelectItem>
            {promptTemplates.length > 0 && (
              <>
                <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground border-t mt-1 pt-2">
                  Custom Perspectives
                </div>
                {promptTemplates.map((template) => (
                  <SelectItem key={template.id} value={`template:${template.id}`}>
                    <span className="flex items-center gap-2">
                      <FileCode className="h-3 w-3" />
                      {template.name}
                    </span>
                  </SelectItem>
                ))}
              </>
            )}
          </SelectContent>
        </Select>
        {formData.prompt_template_id && (
          <p className="text-xs text-muted-foreground">
            Using custom template. Summary length still controls model selection.
          </p>
        )}
      </div>

      {/* Low Activity Mode */}
      <div className="flex items-start space-x-3 rounded-md border p-3">
        <Checkbox
          id="low-activity"
          checked={formData.min_messages === 1}
          onCheckedChange={(checked) =>
            onChange({
              ...formData,
              min_messages: checked ? 1 : 5,
            })
          }
        />
        <div className="space-y-1">
          <label htmlFor="low-activity" className="text-sm font-medium cursor-pointer">
            Allow low activity
          </label>
          <p className="text-xs text-muted-foreground">
            Run even with just 1 message (default requires 5). Useful for support/alert channels.
          </p>
        </div>
      </div>

      {/* ADR-005: Delivery Destinations */}
      <div className="space-y-3">
        <label className="text-sm font-medium">Delivery Destinations</label>
        <p className="text-xs text-muted-foreground">
          Choose where summaries should be delivered
        </p>

        {/* Dashboard Option */}
        <div className="flex items-start space-x-3 rounded-md border p-3">
          <Checkbox
            id="dest-dashboard"
            checked={formData.destinations.dashboard}
            onCheckedChange={(checked) =>
              onChange({
                ...formData,
                destinations: { ...formData.destinations, dashboard: checked as boolean },
              })
            }
          />
          <div className="space-y-1">
            <label htmlFor="dest-dashboard" className="text-sm font-medium cursor-pointer flex items-center gap-2">
              <Archive className="h-4 w-4" />
              Dashboard (Recommended)
            </label>
            <p className="text-xs text-muted-foreground">
              Store in Summaries tab for review and manual push
            </p>
          </div>
        </div>

        {/* Discord Channel Option */}
        <div className="space-y-2 rounded-md border p-3">
          <div className="flex items-start space-x-3">
            <Checkbox
              id="dest-discord"
              checked={formData.destinations.discord_channel}
              onCheckedChange={(checked) =>
                onChange({
                  ...formData,
                  destinations: { ...formData.destinations, discord_channel: checked as boolean },
                })
              }
            />
            <div className="space-y-1 flex-1">
              <label htmlFor="dest-discord" className="text-sm font-medium cursor-pointer flex items-center gap-2">
                <Hash className="h-4 w-4" />
                Discord Channel
              </label>
              <p className="text-xs text-muted-foreground">
                Post directly to a channel
              </p>
            </div>
          </div>
          {formData.destinations.discord_channel && (
            <Select
              value={formData.destinations.discord_channel_id}
              onValueChange={(v) =>
                onChange({
                  ...formData,
                  destinations: { ...formData.destinations, discord_channel_id: v },
                })
              }
            >
              <SelectTrigger className="mt-2">
                <SelectValue placeholder="Select channel" />
              </SelectTrigger>
              <SelectContent>
                {textChannels.map((channel) => (
                  <SelectItem key={channel.id} value={channel.id}>
                    #{channel.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* ADR-047: Discord DM Option */}
        <div className="space-y-2 rounded-md border p-3">
          <div className="flex items-start space-x-3">
            <Checkbox
              id="dest-discord-dm"
              checked={formData.destinations.discord_dm}
              onCheckedChange={(checked) =>
                onChange({
                  ...formData,
                  destinations: { ...formData.destinations, discord_dm: checked as boolean },
                })
              }
            />
            <div className="space-y-1 flex-1">
              <label htmlFor="dest-discord-dm" className="text-sm font-medium cursor-pointer flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                Discord DM
              </label>
              <p className="text-xs text-muted-foreground">
                Send directly to a user via DM
              </p>
            </div>
          </div>
          {formData.destinations.discord_dm && (
            <Input
              className="mt-2"
              placeholder="Discord User ID (e.g., 123456789012345678)"
              value={formData.destinations.discord_dm_user_id}
              onChange={(e) =>
                onChange({
                  ...formData,
                  destinations: { ...formData.destinations, discord_dm_user_id: e.target.value },
                })
              }
            />
          )}
        </div>

        {/* Webhook Option */}
        <div className="space-y-2 rounded-md border p-3">
          <div className="flex items-start space-x-3">
            <Checkbox
              id="dest-webhook"
              checked={formData.destinations.webhook}
              onCheckedChange={(checked) =>
                onChange({
                  ...formData,
                  destinations: { ...formData.destinations, webhook: checked as boolean },
                })
              }
            />
            <div className="space-y-1 flex-1">
              <label htmlFor="dest-webhook" className="text-sm font-medium cursor-pointer flex items-center gap-2">
                <Globe className="h-4 w-4" />
                Webhook
              </label>
              <p className="text-xs text-muted-foreground">
                Send to external service
              </p>
            </div>
          </div>
          {formData.destinations.webhook && (
            <Input
              className="mt-2"
              placeholder="https://..."
              value={formData.destinations.webhook_url}
              onChange={(e) =>
                onChange({
                  ...formData,
                  destinations: { ...formData.destinations, webhook_url: e.target.value },
                })
              }
            />
          )}
        </div>

        {/* ADR-030: Email Option */}
        <div className="space-y-2 rounded-md border p-3">
          <div className="flex items-start space-x-3">
            <Checkbox
              id="dest-email"
              checked={formData.destinations.email}
              onCheckedChange={(checked) =>
                onChange({
                  ...formData,
                  destinations: { ...formData.destinations, email: checked as boolean },
                })
              }
            />
            <div className="space-y-1 flex-1">
              <label htmlFor="dest-email" className="text-sm font-medium cursor-pointer flex items-center gap-2">
                <Mail className="h-4 w-4" />
                Email
              </label>
              <p className="text-xs text-muted-foreground">
                Send to email addresses (requires SMTP configuration)
              </p>
            </div>
          </div>
          {formData.destinations.email && (
            <Input
              className="mt-2"
              placeholder="team@example.com, manager@example.com"
              value={formData.destinations.email_addresses}
              onChange={(e) =>
                onChange({
                  ...formData,
                  destinations: { ...formData.destinations, email_addresses: e.target.value },
                })
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}

export const getInitialFormData = (): ScheduleFormData => ({
  name: "",
  // ADR-011: Default to channel scope
  scope: "channel",
  channel_ids: [],
  category_id: "",
  schedule_type: "daily",
  schedule_time: "09:00",
  schedule_days: [],
  timezone: getBrowserTimezone(),
  summary_length: "detailed",
  perspective: "general",
  min_messages: 5,  // Default: require 5 messages
  prompt_template_id: null,  // ADR-034: Use default prompt
  platform: "discord",  // ADR-051: Default to Discord
  destinations: {
    dashboard: true, // Default to dashboard
    discord_channel: false,
    discord_channel_id: "",
    discord_dm: false,        // ADR-047
    discord_dm_user_id: "",   // ADR-047
    webhook: false,
    webhook_url: "",
    email: false,           // ADR-030
    email_addresses: "",    // ADR-030
  },
});

// For backwards compatibility
export const initialFormData: ScheduleFormData = getInitialFormData();

export function scheduleToFormData(schedule: Schedule): ScheduleFormData {
  // Extract destinations from schedule
  const dashboardDest = schedule.destinations.find((d) => d.type === "dashboard");
  const discordDest = schedule.destinations.find((d) => d.type === "discord_channel");
  const discordDmDest = schedule.destinations.find((d) => d.type === "discord_dm");  // ADR-047
  const webhookDest = schedule.destinations.find((d) => d.type === "webhook");
  const emailDest = schedule.destinations.find((d) => d.type === "email");  // ADR-030

  // ADR-011: Extract scope from schedule
  const scope = (schedule.scope as ScopeType) || "channel";

  return {
    name: schedule.name,
    scope,
    channel_ids: schedule.channel_ids || [],
    category_id: schedule.category_id || "",
    schedule_type: schedule.schedule_type,
    schedule_time: schedule.schedule_time,
    schedule_days: schedule.schedule_days || [],
    timezone: schedule.timezone,
    summary_length: schedule.summary_options.summary_length,
    perspective: schedule.summary_options.perspective,
    min_messages: schedule.summary_options.min_messages ?? 5,
    prompt_template_id: schedule.prompt_template_id || null,  // ADR-034
    platform: schedule.platform || "discord",  // ADR-051
    destinations: {
      dashboard: !!dashboardDest,
      discord_channel: !!discordDest,
      discord_channel_id: discordDest?.target || "",
      discord_dm: !!discordDmDest,           // ADR-047
      discord_dm_user_id: discordDmDest?.target || "",  // ADR-047
      webhook: !!webhookDest,
      webhook_url: webhookDest?.target || "",
      email: !!emailDest,                    // ADR-030
      email_addresses: emailDest?.target || "",  // ADR-030
    },
  };
}

// Helper to convert form destinations to API format
export function formDataToDestinations(formData: ScheduleFormData): Destination[] {
  const destinations: Destination[] = [];

  if (formData.destinations.dashboard) {
    destinations.push({
      type: "dashboard",
      target: "default",
      format: "embed",
    });
  }

  if (formData.destinations.discord_channel && formData.destinations.discord_channel_id) {
    destinations.push({
      type: "discord_channel",
      target: formData.destinations.discord_channel_id,
      format: "embed",
    });
  }

  // ADR-047: Discord DM destination
  if (formData.destinations.discord_dm && formData.destinations.discord_dm_user_id) {
    destinations.push({
      type: "discord_dm",
      target: formData.destinations.discord_dm_user_id,
      format: "embed",
    });
  }

  if (formData.destinations.webhook && formData.destinations.webhook_url) {
    destinations.push({
      type: "webhook",
      target: formData.destinations.webhook_url,
      format: "json",
    });
  }

  // ADR-030: Email destination
  if (formData.destinations.email && formData.destinations.email_addresses) {
    destinations.push({
      type: "email",
      target: formData.destinations.email_addresses,
      format: "html",
    });
  }

  return destinations;
}
