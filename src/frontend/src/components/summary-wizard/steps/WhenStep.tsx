/**
 * Step 2: When (ADR-089)
 *
 * Three options: Now, Recurring, Past
 * Each expands to show relevant options
 */

import { WhenTypeCard } from "../shared/WhenTypeCard";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { CalendarIcon } from "lucide-react";
import { format, subDays, subWeeks, subMonths } from "date-fns";
import { cn } from "@/lib/utils";
import type { StepProps, WhenType, TimeRange, ScheduleFrequency } from "../types";

const TIMEZONES = [
  "America/Toronto",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Asia/Tokyo",
  "Asia/Singapore",
  "Australia/Sydney",
  "UTC",
];

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function WhenStep({ state, onChange }: StepProps) {
  const handleWhenTypeChange = (whenType: WhenType) => {
    onChange({ whenType });
  };

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-medium">When do you want this summary?</h3>

      {/* When Type Selection - Order: Past, Recent (Now), Future (Recurring) */}
      <div className="grid grid-cols-3 gap-3">
        <WhenTypeCard
          whenType="past"
          selected={state.whenType === "past"}
          onClick={() => handleWhenTypeChange("past")}
        />
        <WhenTypeCard
          whenType="now"
          selected={state.whenType === "now"}
          onClick={() => handleWhenTypeChange("now")}
        />
        <WhenTypeCard
          whenType="recurring"
          selected={state.whenType === "recurring"}
          onClick={() => handleWhenTypeChange("recurring")}
        />
      </div>

      {/* Conditional Options */}
      <div className="border rounded-lg p-4 bg-muted/30">
        {state.whenType === "now" && (
          <NowOptions state={state} onChange={onChange} />
        )}
        {state.whenType === "recurring" && (
          <RecurringOptions state={state} onChange={onChange} />
        )}
        {state.whenType === "past" && (
          <PastOptions state={state} onChange={onChange} />
        )}
      </div>
    </div>
  );
}

function NowOptions({ state, onChange }: Pick<StepProps, "state" | "onChange">) {
  const timeRanges: { value: TimeRange; label: string }[] = [
    { value: "4h", label: "4 hours" },
    { value: "8h", label: "8 hours" },
    { value: "24h", label: "24 hours" },
    { value: "48h", label: "48 hours" },
    { value: "custom", label: "Custom" },
  ];

  return (
    <div className="space-y-4">
      <Label>Time range</Label>
      <div className="flex flex-wrap gap-2">
        {timeRanges.map((tr) => (
          <Button
            key={tr.value}
            type="button"
            variant={state.timeRange === tr.value ? "default" : "outline"}
            size="sm"
            onClick={() => onChange({ timeRange: tr.value })}
          >
            {tr.label}
          </Button>
        ))}
      </div>

      {state.timeRange === "custom" && (
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={1}
            max={168}
            value={state.customHours || ""}
            onChange={(e) => onChange({ customHours: parseInt(e.target.value) || undefined })}
            className="w-24"
          />
          <span className="text-sm text-muted-foreground">hours</span>
        </div>
      )}

      <p className="text-sm text-muted-foreground">
        Summary will be generated immediately for the selected time range.
      </p>
    </div>
  );
}

function RecurringOptions({ state, onChange }: Pick<StepProps, "state" | "onChange">) {
  const frequencies: { value: ScheduleFrequency; label: string }[] = [
    { value: "fifteen-minutes", label: "Every 15 min" },
    { value: "hourly", label: "Hourly" },
    { value: "every-4-hours", label: "Every 4 hours" },
    { value: "daily", label: "Daily" },
    { value: "weekly", label: "Weekly" },
    { value: "monthly", label: "Monthly" },
    { value: "once", label: "Once" },
  ];

  const lookbackOptions = [
    { value: 4, label: "4 hours" },
    { value: 8, label: "8 hours" },
    { value: 24, label: "24 hours" },
    { value: 48, label: "48 hours" },
    { value: 168, label: "7 days" },
  ];

  // Interval schedules don't need time picker
  const isIntervalSchedule = ["fifteen-minutes", "hourly", "every-4-hours"].includes(state.frequency);

  const toggleDay = (day: number) => {
    const newDays = state.scheduleDays.includes(day)
      ? state.scheduleDays.filter((d) => d !== day)
      : [...state.scheduleDays, day];
    onChange({ scheduleDays: newDays });
  };

  return (
    <div className="space-y-4">
      {/* Frequency */}
      <div>
        <Label>Frequency</Label>
        <div className="flex gap-2 mt-2">
          {frequencies.map((f) => (
            <Button
              key={f.value}
              type="button"
              variant={state.frequency === f.value ? "default" : "outline"}
              size="sm"
              onClick={() => onChange({ frequency: f.value })}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Day picker for weekly */}
      {state.frequency === "weekly" && (
        <div>
          <Label>Days</Label>
          <div className="flex gap-1 mt-2">
            {DAYS.map((day, i) => (
              <Button
                key={day}
                type="button"
                variant={state.scheduleDays.includes(i) ? "default" : "outline"}
                size="sm"
                className="w-10"
                onClick={() => toggleDay(i)}
              >
                {day}
              </Button>
            ))}
          </div>
        </div>
      )}

      {/* Time and Timezone - hidden for interval schedules */}
      {!isIntervalSchedule && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Time</Label>
            <Input
              type="time"
              value={state.scheduleTime}
              onChange={(e) => onChange({ scheduleTime: e.target.value })}
              className="mt-2"
            />
          </div>
          <div>
            <Label>Timezone</Label>
            <Select
              value={state.timezone}
              onValueChange={(v) => onChange({ timezone: v })}
            >
              <SelectTrigger className="mt-2">
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
        </div>
      )}

      {/* Lookback Hours */}
      <div>
        <Label>Look back period</Label>
        <div className="flex gap-2 mt-2 flex-wrap">
          {lookbackOptions.map((opt) => (
            <Button
              key={opt.value}
              type="button"
              variant={state.lookbackHours === opt.value ? "default" : "outline"}
              size="sm"
              onClick={() => onChange({ lookbackHours: opt.value })}
            >
              {opt.label}
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          How many hours of messages to include in each summary
        </p>
      </div>

      {/* Schedule Name */}
      <div>
        <Label>Schedule name</Label>
        <Input
          value={state.scheduleName}
          onChange={(e) => onChange({ scheduleName: e.target.value })}
          placeholder="e.g., Weekly team summary"
          className="mt-2"
        />
      </div>

      {/* Continuity for weekly */}
      {state.frequency === "weekly" && (
        <div className="flex items-start space-x-3 p-3 rounded-md border bg-background">
          <Checkbox
            id="continuity"
            checked={state.enableContinuity}
            onCheckedChange={(checked) => onChange({ enableContinuity: !!checked })}
          />
          <div>
            <label htmlFor="continuity" className="text-sm font-medium cursor-pointer">
              Enable week-to-week continuity
            </label>
            <p className="text-xs text-muted-foreground">
              Each week's summary includes context from the previous week
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function PastOptions({ state, onChange }: Pick<StepProps, "state" | "onChange">) {
  const quickRanges = [
    { label: "Last week", from: subWeeks(new Date(), 1), to: new Date() },
    { label: "Last month", from: subMonths(new Date(), 1), to: new Date() },
    { label: "Last 90 days", from: subDays(new Date(), 90), to: new Date() },
  ];

  const handleQuickRange = (from: Date, to: Date) => {
    onChange({ dateFrom: from, dateTo: to });
  };

  return (
    <div className="space-y-4">
      {/* Quick Ranges */}
      <div>
        <Label>Quick select</Label>
        <div className="flex gap-2 mt-2">
          {quickRanges.map((r) => (
            <Button
              key={r.label}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => handleQuickRange(r.from, r.to)}
            >
              {r.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Custom Date Range */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>From</Label>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                className={cn(
                  "w-full justify-start text-left font-normal mt-2",
                  !state.dateFrom && "text-muted-foreground"
                )}
              >
                <CalendarIcon className="mr-2 h-4 w-4" />
                {state.dateFrom ? format(state.dateFrom, "PPP") : "Pick a date"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0">
              <Calendar
                mode="single"
                selected={state.dateFrom || undefined}
                onSelect={(date) => onChange({ dateFrom: date || null })}
                initialFocus
              />
            </PopoverContent>
          </Popover>
        </div>
        <div>
          <Label>To</Label>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                className={cn(
                  "w-full justify-start text-left font-normal mt-2",
                  !state.dateTo && "text-muted-foreground"
                )}
              >
                <CalendarIcon className="mr-2 h-4 w-4" />
                {state.dateTo ? format(state.dateTo, "PPP") : "Pick a date"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0">
              <Calendar
                mode="single"
                selected={state.dateTo || undefined}
                onSelect={(date) => onChange({ dateTo: date || null })}
                initialFocus
              />
            </PopoverContent>
          </Popover>
        </div>
      </div>

      {/* Granularity */}
      <div>
        <Label>Granularity</Label>
        <div className="flex gap-4 mt-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              checked={state.pastGranularity === "single"}
              onChange={() => onChange({ pastGranularity: "single" })}
              className="h-4 w-4"
            />
            <span className="text-sm">One summary for entire period</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              checked={state.pastGranularity === "daily"}
              onChange={() => onChange({ pastGranularity: "daily" })}
              className="h-4 w-4"
            />
            <span className="text-sm">Daily summaries</span>
          </label>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        {state.pastGranularity === "single"
          ? "One summary covering the entire date range will be generated."
          : "A separate summary will be generated for each day in the range."}
      </p>
    </div>
  );
}
