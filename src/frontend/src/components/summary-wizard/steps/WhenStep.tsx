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

// Generate auto-name based on selected options - exported for use in submission
export function generateScheduleName(state: Pick<StepProps, "state">["state"]): string {
  const parts: string[] = [];

  // For weekly schedules with specific days, lead with the day(s)
  if (state.frequency === "weekly" && state.scheduleDays.length > 0) {
    const dayNames = state.scheduleDays
      .sort((a, b) => a - b)
      .map((d) => DAYS[d])
      .join("/");
    parts.push(dayNames);
  }

  // Rolling period takes precedence for schedule type description
  if (state.rollingPeriod && state.rollingPeriod !== "none") {
    const rollingLabels: Record<string, string> = {
      weekly: "Weekly",
      biweekly: "Biweekly",
      monthly: "Monthly",
    };
    parts.push(rollingLabels[state.rollingPeriod] || state.rollingPeriod);
    parts.push("Digest");
  } else {
    // Non-rolling: describe the frequency
    const freqLabels: Record<ScheduleFrequency, string> = {
      "fifteen-minutes": "15-Minute",
      "hourly": "Hourly",
      "every-4-hours": "4-Hour",
      "daily": "Daily",
      "weekly": "Weekly",
      "monthly": "Monthly",
      "once": "One-Time",
    };
    parts.push(freqLabels[state.frequency]);
    parts.push("Summary");
  }

  return parts.join(" ");
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

  // Determine valid rolling period options based on frequency
  // Rolling periods need multiple runs within the period to accumulate
  const getValidRollingPeriods = (freq: ScheduleFrequency) => {
    switch (freq) {
      case "fifteen-minutes":
      case "hourly":
      case "every-4-hours":
      case "daily":
        // High frequency: all rolling periods valid
        return ["none", "weekly", "biweekly", "monthly"] as const;
      case "weekly":
        // Weekly runs: can't do weekly rolling (only 1 run), but biweekly/monthly work
        return ["none", "biweekly", "monthly"] as const;
      case "monthly":
      case "once":
        // Too infrequent for any rolling accumulation
        return ["none"] as const;
      default:
        return ["none"] as const;
    }
  };

  const validRollingPeriods = getValidRollingPeriods(state.frequency);
  const canUseRolling = validRollingPeriods.length > 1;

  // Auto-reset rolling period if frequency changes to incompatible
  const handleFrequencyChange = (newFreq: ScheduleFrequency) => {
    const newValidPeriods = getValidRollingPeriods(newFreq);
    const updates: Partial<typeof state> = { frequency: newFreq };

    // Reset rolling period if current selection is no longer valid
    if (state.rollingPeriod !== "none" && !newValidPeriods.includes(state.rollingPeriod as any)) {
      updates.rollingPeriod = "none";
    }

    onChange(updates);
  };

  const toggleDay = (day: number) => {
    const newDays = state.scheduleDays.includes(day)
      ? state.scheduleDays.filter((d) => d !== day)
      : [...state.scheduleDays, day];
    onChange({ scheduleDays: newDays });
  };

  // Auto-generate name when options change
  const autoName = generateScheduleName(state);

  return (
    <div className="space-y-4">
      {/* Frequency */}
      <div>
        <Label>Frequency</Label>
        <div className="flex gap-2 mt-2 flex-wrap">
          {frequencies.map((f) => (
            <Button
              key={f.value}
              type="button"
              variant={state.frequency === f.value ? "default" : "outline"}
              size="sm"
              onClick={() => handleFrequencyChange(f.value)}
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

      {/* ADR-101: Rolling Period Summaries (ADR-102: Frequency constraints) */}
      <div className="space-y-3 p-3 rounded-md border bg-background">
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-sm font-medium">Rolling period summary</Label>
            <p className="text-xs text-muted-foreground">
              Accumulate runs into a single period summary
            </p>
          </div>
          <Select
            value={state.rollingPeriod}
            onValueChange={(v) => onChange({ rollingPeriod: v as "none" | "weekly" | "biweekly" | "monthly" })}
            disabled={!canUseRolling}
          >
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Off</SelectItem>
              <SelectItem value="weekly" disabled={!validRollingPeriods.includes("weekly")}>
                Weekly
              </SelectItem>
              <SelectItem value="biweekly" disabled={!validRollingPeriods.includes("biweekly")}>
                Biweekly
              </SelectItem>
              <SelectItem value="monthly" disabled={!validRollingPeriods.includes("monthly")}>
                Monthly
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Explanation when rolling is unavailable or limited */}
        {!canUseRolling && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Rolling periods require a more frequent schedule to accumulate multiple runs.
            {state.frequency === "monthly" && " Monthly schedules only run once per period."}
            {state.frequency === "once" && " One-time schedules cannot accumulate."}
          </p>
        )}
        {canUseRolling && state.frequency === "weekly" && !validRollingPeriods.includes("weekly") && (
          <p className="text-xs text-muted-foreground">
            Weekly rolling requires a more frequent schedule (daily or more) to accumulate multiple runs within the week.
          </p>
        )}

        {state.rollingPeriod !== "none" && (
          <>
            {/* End day for weekly rolling */}
            {state.rollingPeriod === "weekly" && (
              <div className="flex items-center gap-3">
                <Label className="text-sm">Finalize on</Label>
                <div className="flex gap-1">
                  {DAYS.map((day, i) => (
                    <Button
                      key={day}
                      type="button"
                      variant={state.rollingEndDay === i ? "default" : "outline"}
                      size="sm"
                      className="w-10"
                      onClick={() => onChange({ rollingEndDay: i })}
                    >
                      {day}
                    </Button>
                  ))}
                </div>
              </div>
            )}

            {/* Accumulation strategy */}
            <div className="flex items-center gap-3">
              <Label className="text-sm">Strategy</Label>
              <Select
                value={state.accumulationStrategy}
                onValueChange={(v) => onChange({ accumulationStrategy: v as "append" | "resummarize" | "hybrid" })}
              >
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="hybrid">Hybrid (recommended)</SelectItem>
                  <SelectItem value="append">Append sections</SelectItem>
                  <SelectItem value="resummarize">Re-summarize all</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <p className="text-xs text-muted-foreground">
              {state.rollingPeriod === "weekly" && (
                <>Runs accumulate into one summary until {DAYS[state.rollingEndDay]}, then a new period starts.</>
              )}
              {state.rollingPeriod === "biweekly" && (
                <>Content accumulates for two weeks before finalizing and starting fresh.</>
              )}
              {state.rollingPeriod === "monthly" && (
                <>Content accumulates until month-end, then a new period starts.</>
              )}
            </p>
          </>
        )}
      </div>

      {/* Schedule Name with auto-generated suggestion */}
      <div>
        <Label>Schedule name</Label>
        <div className="flex gap-2 mt-2">
          <Input
            value={state.scheduleName}
            onChange={(e) => onChange({ scheduleName: e.target.value })}
            placeholder={autoName}
            className="flex-1"
          />
          {state.scheduleName !== autoName && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onChange({ scheduleName: autoName })}
              title="Use auto-generated name"
            >
              Auto
            </Button>
          )}
        </div>
        {!state.scheduleName && (
          <p className="text-xs text-muted-foreground mt-1">
            Will use: {autoName}
          </p>
        )}
      </div>
    </div>
  );
}

function PastOptions({ state, onChange }: Pick<StepProps, "state" | "onChange">) {
  const quickRanges = [
    { label: "Last week", from: subWeeks(new Date(), 1), to: new Date() },
    { label: "Last month", from: subMonths(new Date(), 1), to: new Date() },
    { label: "Last 90 days", from: subDays(new Date(), 90), to: new Date() },
  ];

  const lookbackOptions = [
    { value: 4, label: "4 hours" },
    { value: 8, label: "8 hours" },
    { value: 24, label: "24 hours" },
    { value: 48, label: "48 hours" },
    { value: 168, label: "7 days" },
  ];

  const handleQuickRange = (from: Date, to: Date) => {
    onChange({ dateFrom: from, dateTo: to });
  };

  const toggleDay = (day: number) => {
    const newDays = state.pastScheduleDays.includes(day)
      ? state.pastScheduleDays.filter((d) => d !== day)
      : [...state.pastScheduleDays, day];
    onChange({ pastScheduleDays: newDays });
  };

  return (
    <div className="space-y-4">
      {/* Quick Ranges */}
      <div>
        <Label>Date range</Label>
        <div className="flex gap-2 mt-2 flex-wrap">
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
        <div className="flex gap-2 mt-2 flex-wrap">
          <Button
            type="button"
            variant={state.pastGranularity === "single" ? "default" : "outline"}
            size="sm"
            onClick={() => onChange({ pastGranularity: "single" })}
          >
            Single
          </Button>
          <Button
            type="button"
            variant={state.pastGranularity === "daily" ? "default" : "outline"}
            size="sm"
            onClick={() => onChange({ pastGranularity: "daily" })}
          >
            Daily
          </Button>
          <Button
            type="button"
            variant={state.pastGranularity === "weekly" ? "default" : "outline"}
            size="sm"
            onClick={() => onChange({ pastGranularity: "weekly" })}
          >
            Weekly
          </Button>
        </div>
      </div>

      {/* Day picker for weekly */}
      {state.pastGranularity === "weekly" && (
        <div>
          <Label>Generate on</Label>
          <div className="flex gap-1 mt-2">
            {DAYS.map((day, i) => (
              <Button
                key={day}
                type="button"
                variant={state.pastScheduleDays.includes(i) ? "default" : "outline"}
                size="sm"
                className="w-10"
                onClick={() => toggleDay(i)}
              >
                {day}
              </Button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            A summary will be generated for each selected day in the date range
          </p>
        </div>
      )}

      {/* Lookback Hours - for weekly and daily */}
      {state.pastGranularity !== "single" && (
        <div>
          <Label>Look back period</Label>
          <div className="flex gap-2 mt-2 flex-wrap">
            {lookbackOptions.map((opt) => (
              <Button
                key={opt.value}
                type="button"
                variant={state.pastLookbackHours === opt.value ? "default" : "outline"}
                size="sm"
                onClick={() => onChange({ pastLookbackHours: opt.value })}
              >
                {opt.label}
              </Button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            How many hours of messages to include in each summary
          </p>
        </div>
      )}

      {/* Per-channel option for weekly */}
      {state.pastGranularity === "weekly" && (
        <div className="flex items-start space-x-3 p-3 rounded-md border bg-background">
          <Checkbox
            id="perChannel"
            checked={state.perChannel}
            onCheckedChange={(checked) => onChange({ perChannel: !!checked })}
          />
          <div>
            <label htmlFor="perChannel" className="text-sm font-medium cursor-pointer">
              Generate per-channel summaries
            </label>
            <p className="text-xs text-muted-foreground">
              Create one summary per channel instead of one combined server summary.
              Better for active servers with many channels.
            </p>
          </div>
        </div>
      )}

      {/* Force Regenerate option */}
      <div className="flex items-start space-x-3 p-3 rounded-md border bg-background">
        <Checkbox
          id="forceRegenerate"
          checked={state.forceRegenerate}
          onCheckedChange={(checked) => onChange({ forceRegenerate: !!checked })}
        />
        <div>
          <label htmlFor="forceRegenerate" className="text-sm font-medium cursor-pointer">
            Force regenerate existing summaries
          </label>
          <p className="text-xs text-muted-foreground">
            Delete and recreate summaries that already exist for these dates
          </p>
        </div>
      </div>

      {/* Description of what will happen */}
      <div className="p-3 rounded-md bg-muted/50 text-sm text-muted-foreground">
        {state.pastGranularity === "single" && (
          <>One summary covering the entire date range will be generated.</>
        )}
        {state.pastGranularity === "daily" && (
          <>A separate summary will be generated for each day, looking back {state.pastLookbackHours} hours.</>
        )}
        {state.pastGranularity === "weekly" && state.pastScheduleDays.length > 0 && (
          <>
            Weekly summaries will be generated for every{" "}
            {state.pastScheduleDays.sort((a, b) => a - b).map((d) => DAYS[d]).join(", ")}{" "}
            in the date range, each covering {state.pastLookbackHours} hours.
          </>
        )}
        {state.pastGranularity === "weekly" && state.pastScheduleDays.length === 0 && (
          <>Select at least one day to generate weekly summaries.</>
        )}
      </div>
    </div>
  );
}
