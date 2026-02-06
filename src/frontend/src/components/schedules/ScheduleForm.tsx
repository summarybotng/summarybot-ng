import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Schedule, SummaryOptions } from "@/types";

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
}

interface ScheduleFormProps {
  formData: ScheduleFormData;
  onChange: (data: ScheduleFormData) => void;
}

export function ScheduleForm({ formData, onChange }: ScheduleFormProps) {
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
};

export function scheduleToFormData(schedule: Schedule): ScheduleFormData {
  return {
    name: schedule.name,
    schedule_type: schedule.schedule_type,
    schedule_time: schedule.schedule_time,
    schedule_days: schedule.schedule_days || [],
    timezone: schedule.timezone,
    summary_length: schedule.summary_options.summary_length,
    perspective: schedule.summary_options.perspective,
  };
}
