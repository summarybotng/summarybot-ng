/**
 * Summary Filters Component (ADR-017, ADR-018)
 *
 * Provides filtering, sorting, and view options for the stored summaries list.
 * Includes date range, sort controls, channel mode, integrity filters, and content filters.
 */

import { useState } from "react";
import { format } from "date-fns";
import { Calendar as CalendarIcon, ArrowUpDown, Filter, X, Hash, AlertTriangle, CheckCircle2, ListChecks, Users, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  SummarySourceType,
  ChannelModeType,
  SortByType,
  SortOrderType,
} from "@/hooks/useStoredSummaries";

export interface FilterState {
  source: SummarySourceType;
  archived: boolean;
  createdAfter?: string;
  createdBefore?: string;
  archivePeriod?: string;
  channelMode: ChannelModeType;
  hasGrounding?: boolean;
  sortBy: SortByType;
  sortOrder: SortOrderType;
  // ADR-018: Content filters
  hasKeyPoints?: boolean;
  hasActionItems?: boolean;
  hasParticipants?: boolean;
  minMessageCount?: number;
  maxMessageCount?: number;
}

interface SummaryFiltersProps {
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  totalCount: number;
}

export function SummaryFilters({ filters, onFiltersChange, totalCount }: SummaryFiltersProps) {
  const [dateRangeOpen, setDateRangeOpen] = useState(false);

  const activeFilterCount = [
    filters.createdAfter,
    filters.createdBefore,
    filters.channelMode !== "all",
    filters.hasGrounding !== undefined,
    // ADR-018: Content filter counts
    filters.hasKeyPoints !== undefined,
    filters.hasActionItems !== undefined,
    filters.hasParticipants !== undefined,
    filters.minMessageCount !== undefined,
    filters.maxMessageCount !== undefined,
  ].filter(Boolean).length;

  const handleClearFilters = () => {
    onFiltersChange({
      ...filters,
      createdAfter: undefined,
      createdBefore: undefined,
      archivePeriod: undefined,
      channelMode: "all",
      hasGrounding: undefined,
      // ADR-018: Clear content filters
      hasKeyPoints: undefined,
      hasActionItems: undefined,
      hasParticipants: undefined,
      minMessageCount: undefined,
      maxMessageCount: undefined,
    });
  };

  return (
    <div className="space-y-3">
      {/* Main filter row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Source filter */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Source:</span>
          <Select
            value={filters.source}
            onValueChange={(v) => onFiltersChange({ ...filters, source: v as SummarySourceType })}
          >
            <SelectTrigger className="w-[130px] h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sources</SelectItem>
              <SelectItem value="realtime">Real-time</SelectItem>
              <SelectItem value="scheduled">Scheduled</SelectItem>
              <SelectItem value="archive">Archive</SelectItem>
              <SelectItem value="manual">Manual</SelectItem>
              <SelectItem value="imported">Imported</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Date range filter */}
        <Popover open={dateRangeOpen} onOpenChange={setDateRangeOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className={cn(
                "h-8 justify-start text-left font-normal",
                (filters.createdAfter || filters.createdBefore) && "border-primary"
              )}
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {filters.createdAfter || filters.createdBefore ? (
                <span>
                  {filters.createdAfter && format(new Date(filters.createdAfter), "MMM d")}
                  {filters.createdAfter && filters.createdBefore && " - "}
                  {filters.createdBefore && format(new Date(filters.createdBefore), "MMM d")}
                </span>
              ) : (
                <span>Date Range</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <DateRangeSelector
              from={filters.createdAfter ? new Date(filters.createdAfter) : undefined}
              to={filters.createdBefore ? new Date(filters.createdBefore) : undefined}
              onSelect={(from, to) => {
                onFiltersChange({
                  ...filters,
                  createdAfter: from?.toISOString(),
                  createdBefore: to?.toISOString(),
                });
              }}
              onClear={() => {
                onFiltersChange({
                  ...filters,
                  createdAfter: undefined,
                  createdBefore: undefined,
                });
                setDateRangeOpen(false);
              }}
            />
          </PopoverContent>
        </Popover>

        {/* Sort controls */}
        <div className="flex items-center gap-2">
          <Select
            value={filters.sortBy}
            onValueChange={(v) => onFiltersChange({ ...filters, sortBy: v as SortByType })}
          >
            <SelectTrigger className="w-[140px] h-8">
              <ArrowUpDown className="mr-2 h-3 w-3" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="created_at">Created Date</SelectItem>
              <SelectItem value="message_count">Message Count</SelectItem>
              <SelectItem value="archive_period">Archive Period</SelectItem>
            </SelectContent>
          </Select>

          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() =>
              onFiltersChange({
                ...filters,
                sortOrder: filters.sortOrder === "desc" ? "asc" : "desc",
              })
            }
          >
            <span className="sr-only">Toggle sort order</span>
            {filters.sortOrder === "desc" ? "↓" : "↑"}
          </Button>
        </div>

        {/* More filters dropdown */}
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className={cn(
                "h-8",
                activeFilterCount > 0 && "border-primary"
              )}
            >
              <Filter className="mr-2 h-4 w-4" />
              Filters
              {activeFilterCount > 0 && (
                <Badge variant="secondary" className="ml-2 h-5 px-1.5">
                  {activeFilterCount}
                </Badge>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72" align="start">
            <div className="space-y-4">
              <h4 className="font-medium text-sm">Additional Filters</h4>

              {/* Channel mode */}
              <div className="space-y-2">
                <label className="text-sm text-muted-foreground flex items-center gap-2">
                  <Hash className="h-3 w-3" />
                  Channel Mode
                </label>
                <Select
                  value={filters.channelMode}
                  onValueChange={(v) =>
                    onFiltersChange({ ...filters, channelMode: v as ChannelModeType })
                  }
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="single">Single Channel</SelectItem>
                    <SelectItem value="multi">Multi-Channel</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Grounding filter */}
              <div className="space-y-2">
                <label className="text-sm text-muted-foreground">Data Quality</label>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant={filters.hasGrounding === true ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      onFiltersChange({
                        ...filters,
                        hasGrounding: filters.hasGrounding === true ? undefined : true,
                      })
                    }
                  >
                    <CheckCircle2 className="mr-1 h-3 w-3" />
                    With Grounding
                  </Button>
                  <Button
                    variant={filters.hasGrounding === false ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      onFiltersChange({
                        ...filters,
                        hasGrounding: filters.hasGrounding === false ? undefined : false,
                      })
                    }
                  >
                    <AlertTriangle className="mr-1 h-3 w-3" />
                    No Grounding
                  </Button>
                </div>
              </div>

              {/* ADR-018: Content filters */}
              <div className="space-y-2">
                <label className="text-sm text-muted-foreground flex items-center gap-2">
                  <ListChecks className="h-3 w-3" />
                  Content
                </label>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant={filters.hasKeyPoints === true ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      onFiltersChange({
                        ...filters,
                        hasKeyPoints: filters.hasKeyPoints === true ? undefined : true,
                      })
                    }
                  >
                    Key Points
                  </Button>
                  <Button
                    variant={filters.hasActionItems === true ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      onFiltersChange({
                        ...filters,
                        hasActionItems: filters.hasActionItems === true ? undefined : true,
                      })
                    }
                  >
                    Action Items
                  </Button>
                  <Button
                    variant={filters.hasParticipants === true ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      onFiltersChange({
                        ...filters,
                        hasParticipants: filters.hasParticipants === true ? undefined : true,
                      })
                    }
                  >
                    <Users className="mr-1 h-3 w-3" />
                    Participants
                  </Button>
                </div>
              </div>

              {/* ADR-018: Message count filter */}
              <div className="space-y-2">
                <label className="text-sm text-muted-foreground flex items-center gap-2">
                  <MessageSquare className="h-3 w-3" />
                  Message Count
                </label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    placeholder="Min"
                    className="w-20 h-8"
                    value={filters.minMessageCount ?? ""}
                    onChange={(e) =>
                      onFiltersChange({
                        ...filters,
                        minMessageCount: e.target.value ? parseInt(e.target.value) : undefined,
                      })
                    }
                  />
                  <span className="text-muted-foreground">to</span>
                  <Input
                    type="number"
                    placeholder="Max"
                    className="w-20 h-8"
                    value={filters.maxMessageCount ?? ""}
                    onChange={(e) =>
                      onFiltersChange({
                        ...filters,
                        maxMessageCount: e.target.value ? parseInt(e.target.value) : undefined,
                      })
                    }
                  />
                </div>
              </div>

              {/* Clear filters */}
              {activeFilterCount > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full"
                  onClick={handleClearFilters}
                >
                  <X className="mr-2 h-4 w-4" />
                  Clear Additional Filters
                </Button>
              )}
            </div>
          </PopoverContent>
        </Popover>

        {/* Show archived toggle */}
        <Button
          variant={filters.archived ? "default" : "outline"}
          size="sm"
          className="h-8"
          onClick={() => onFiltersChange({ ...filters, archived: !filters.archived })}
        >
          {filters.archived ? "Showing Archived" : "Show Archived"}
        </Button>

        {/* Results count */}
        <span className="ml-auto text-sm text-muted-foreground">
          {totalCount} {totalCount === 1 ? "summary" : "summaries"}
        </span>
      </div>

      {/* Active filters tags */}
      {activeFilterCount > 0 && (
        <div className="flex flex-wrap gap-2">
          {filters.createdAfter && (
            <Badge variant="secondary" className="gap-1">
              After: {format(new Date(filters.createdAfter), "MMM d, yyyy")}
              <button
                onClick={() => onFiltersChange({ ...filters, createdAfter: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {filters.createdBefore && (
            <Badge variant="secondary" className="gap-1">
              Before: {format(new Date(filters.createdBefore), "MMM d, yyyy")}
              <button
                onClick={() => onFiltersChange({ ...filters, createdBefore: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {filters.channelMode !== "all" && (
            <Badge variant="secondary" className="gap-1">
              {filters.channelMode === "single" ? "Single Channel" : "Multi-Channel"}
              <button
                onClick={() => onFiltersChange({ ...filters, channelMode: "all" })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {filters.hasGrounding !== undefined && (
            <Badge variant="secondary" className="gap-1">
              {filters.hasGrounding ? "With Grounding" : "No Grounding"}
              <button
                onClick={() => onFiltersChange({ ...filters, hasGrounding: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {/* ADR-018: Content filter tags */}
          {filters.hasKeyPoints === true && (
            <Badge variant="secondary" className="gap-1">
              Has Key Points
              <button
                onClick={() => onFiltersChange({ ...filters, hasKeyPoints: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {filters.hasActionItems === true && (
            <Badge variant="secondary" className="gap-1">
              Has Action Items
              <button
                onClick={() => onFiltersChange({ ...filters, hasActionItems: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {filters.hasParticipants === true && (
            <Badge variant="secondary" className="gap-1">
              Has Participants
              <button
                onClick={() => onFiltersChange({ ...filters, hasParticipants: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {(filters.minMessageCount !== undefined || filters.maxMessageCount !== undefined) && (
            <Badge variant="secondary" className="gap-1">
              Messages: {filters.minMessageCount ?? 0} - {filters.maxMessageCount ?? "∞"}
              <button
                onClick={() => onFiltersChange({ ...filters, minMessageCount: undefined, maxMessageCount: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}

// Date range selector subcomponent
interface DateRangeSelectorProps {
  from?: Date;
  to?: Date;
  onSelect: (from?: Date, to?: Date) => void;
  onClear: () => void;
}

function DateRangeSelector({ from, to, onSelect, onClear }: DateRangeSelectorProps) {
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
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">From</label>
            <Calendar
              mode="single"
              selected={internalFrom}
              onSelect={(date) => setInternalFrom(date)}
              disabled={(date) => date > new Date() || (internalTo ? date > internalTo : false)}
              initialFocus
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">To</label>
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
