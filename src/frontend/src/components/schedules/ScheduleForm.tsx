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
import { Archive, Hash, Globe } from "lucide-react";
import type { Schedule, SummaryOptions, Destination, Channel } from "@/types";

const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Asia/Tokyo",
  "Australia/Sydney",
  "UTC",
];

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export interface ScheduleFormData {
  name: string;
  schedule_type: Schedule["schedule_type"];
  schedule_time: string;
  schedule_days: number[];
  timezone: string;
  summary_length: SummaryOptions["summary_length"];
  perspective: SummaryOptions["perspective"];
  // ADR-005: Delivery destinations
  destinations: {
    dashboard: boolean;
    discord_channel: boolean;
    discord_channel_id: string;
    webhook: boolean;
    webhook_url: string;
  };
}

interface ScheduleFormProps {
  formData: ScheduleFormData;
  onChange: (data: ScheduleFormData) => void;
  channels?: Channel[];
}

export function ScheduleForm({ formData, onChange, channels = [] }: ScheduleFormProps) {
  const textChannels = channels.filter((c) => c.type === "text");

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

      <div className="space-y-2">
        <label className="text-sm font-medium">Time</label>
        <Input
          type="time"
          value={formData.schedule_time}
          onChange={(e) => onChange({ ...formData, schedule_time: e.target.value })}
        />
      </div>

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

      <div className="space-y-2">
        <label className="text-sm font-medium">Perspective</label>
        <Select
          value={formData.perspective}
          onValueChange={(v) =>
            onChange({ ...formData, perspective: v as SummaryOptions["perspective"] })
          }
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
          </SelectContent>
        </Select>
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
      </div>
    </div>
  );
}

export const initialFormData: ScheduleFormData = {
  name: "",
  schedule_type: "daily",
  schedule_time: "09:00",
  schedule_days: [],
  timezone: "UTC",
  summary_length: "detailed",
  perspective: "general",
  destinations: {
    dashboard: true, // Default to dashboard
    discord_channel: false,
    discord_channel_id: "",
    webhook: false,
    webhook_url: "",
  },
};

export function scheduleToFormData(schedule: Schedule): ScheduleFormData {
  // Extract destinations from schedule
  const dashboardDest = schedule.destinations.find((d) => d.type === "dashboard");
  const discordDest = schedule.destinations.find((d) => d.type === "discord_channel");
  const webhookDest = schedule.destinations.find((d) => d.type === "webhook");

  return {
    name: schedule.name,
    schedule_type: schedule.schedule_type,
    schedule_time: schedule.schedule_time,
    schedule_days: schedule.schedule_days || [],
    timezone: schedule.timezone,
    summary_length: schedule.summary_options.summary_length,
    perspective: schedule.summary_options.perspective,
    destinations: {
      dashboard: !!dashboardDest,
      discord_channel: !!discordDest,
      discord_channel_id: discordDest?.target || "",
      webhook: !!webhookDest,
      webhook_url: webhookDest?.target || "",
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

  if (formData.destinations.webhook && formData.destinations.webhook_url) {
    destinations.push({
      type: "webhook",
      target: formData.destinations.webhook_url,
      format: "json",
    });
  }

  return destinations;
}
