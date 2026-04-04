/**
 * Date Range Selector Component (ADR-037)
 *
 * Calendar-based date range picker with quick presets.
 * Extracted from SummaryFilters for reuse across filter forms.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";

interface DateRangeSelectorProps {
  from?: Date;
  to?: Date;
  onSelect: (from?: Date, to?: Date) => void;
  onClear: () => void;
}

export function DateRangeSelector({ from, to, onSelect, onClear }: DateRangeSelectorProps) {
  const [internalFrom, setInternalFrom] = useState<Date | undefined>(from);
  const [internalTo, setInternalTo] = useState<Date | undefined>(to);

  const handleApply = () => {
    onSelect(internalFrom, internalTo);
  };

  // Quick presets
  const presets = [
    { label: "Today", days: 0 },
    { label: "Last 7 days", days: 7 },
    { label: "Last 30 days", days: 30 },
    { label: "Last 90 days", days: 90 },
  ];

  const applyPreset = (days: number) => {
    const now = new Date();
    const fromDate = new Date();
    if (days > 0) {
      fromDate.setDate(now.getDate() - days);
    } else {
      fromDate.setHours(0, 0, 0, 0);
    }
    setInternalFrom(fromDate);
    setInternalTo(now);
    onSelect(fromDate, now);
  };

  return (
    <div className="p-3 space-y-3">
      {/* Quick presets */}
      <div className="flex flex-wrap gap-2">
        {presets.map((preset) => (
          <Button
            key={preset.label}
            variant="outline"
            size="sm"
            onClick={() => applyPreset(preset.days)}
          >
            {preset.label}
          </Button>
        ))}
      </div>

      <div className="border-t pt-3">
        <div className="flex gap-6 justify-center">
          <div className="flex flex-col items-center">
            <label className="text-xs text-muted-foreground mb-2 font-medium">From</label>
            <Calendar
              mode="single"
              selected={internalFrom}
              onSelect={(date) => setInternalFrom(date)}
              disabled={(date) => date > new Date() || (internalTo ? date > internalTo : false)}
              initialFocus
            />
          </div>
          <div className="flex flex-col items-center">
            <label className="text-xs text-muted-foreground mb-2 font-medium">To</label>
            <Calendar
              mode="single"
              selected={internalTo}
              onSelect={(date) => setInternalTo(date)}
              disabled={(date) => date > new Date() || (internalFrom ? date < internalFrom : false)}
            />
          </div>
        </div>
      </div>

      <div className="flex justify-between border-t pt-3">
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear
        </Button>
        <Button size="sm" onClick={handleApply}>
          Apply
        </Button>
      </div>
    </div>
  );
}
