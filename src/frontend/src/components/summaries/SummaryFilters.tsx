/**
 * Summary Filters Component (ADR-017, ADR-018, ADR-037)
 *
 * Provides filtering, sorting, and view options for the stored summaries list.
 * Includes date range, sort controls, channel mode, integrity filters, and content filters.
 * ADR-037: Uses centralized SummaryFilterCriteria type.
 */

import { useState, useEffect, useCallback } from "react";
import { format, parse } from "date-fns";
import { Calendar as CalendarIcon, ArrowUpDown, Filter, X, Hash, AlertTriangle, CheckCircle2, ListChecks, Users, MessageSquare, Lock, Search } from "lucide-react";
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
  SummaryFilterCriteria,
  SummarySourceType,
  ChannelModeType,
  SortByType,
  SortOrderType,
} from "@/types/filters";
import { usePerspectiveOptions } from "@/components/filters";

// ADR-037: FilterState is now an alias for SummaryFilterCriteria with required defaults
export interface FilterState extends SummaryFilterCriteria {
  source: SummarySourceType;
  channelMode: ChannelModeType;
  sortBy: SortByType;
  sortOrder: SortOrderType;
  archived: boolean;
}

interface SummaryFiltersProps {
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  totalCount: number;
  guildId?: string;
}

// Number input that only submits on blur or Enter (prevents auto-submit while typing)
interface DebouncedNumberInputProps {
  value: number | undefined;
  onChange: (value: number | undefined) => void;
  placeholder?: string;
  className?: string;
  min?: number;
}

function DebouncedNumberInput({ value, onChange, placeholder, className, min }: DebouncedNumberInputProps) {
  const [localValue, setLocalValue] = useState(value?.toString() ?? "");

  // Sync local value when external value changes
  useEffect(() => {
    setLocalValue(value?.toString() ?? "");
  }, [value]);

  const handleCommit = useCallback(() => {
    const parsed = localValue ? parseInt(localValue, 10) : undefined;
    if (parsed !== value) {
      onChange(parsed);
    }
  }, [localValue, value, onChange]);

  return (
    <Input
      type="number"
      placeholder={placeholder}
      className={className}
      min={min}
      value={localValue}
      onChange={(e) => setLocalValue(e.target.value)}
      onBlur={handleCommit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          handleCommit();
        }
      }}
    />
  );
}

export function SummaryFilters({ filters, onFiltersChange, totalCount, guildId }: SummaryFiltersProps) {
  const [dateRangeOpen, setDateRangeOpen] = useState(false);
  const [searchInput, setSearchInput] = useState(filters.searchQuery || "");
  const { perspectives } = usePerspectiveOptions(guildId);

  // Sync searchInput when external filter changes
  useEffect(() => {
    setSearchInput(filters.searchQuery || "");
  }, [filters.searchQuery]);

  // Debounced search - commits on blur or Enter
  const handleSearchCommit = useCallback(() => {
    const trimmed = searchInput.trim();
    if (trimmed !== (filters.searchQuery || "")) {
      onFiltersChange({ ...filters, searchQuery: trimmed || undefined });
    }
  }, [searchInput, filters, onFiltersChange]);

  // Split perspectives into standard (system) and custom
  const standardPerspectives = perspectives.filter(p => !p.isCustom);
  const customPerspectives = perspectives.filter(p => p.isCustom);

  const activeFilterCount = [
    filters.searchQuery,  // Text search
    filters.archivePeriod,  // Calendar date selection
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
    // ADR-021: Content count filter counts
    filters.minKeyPoints !== undefined || filters.maxKeyPoints !== undefined,
    filters.minActionItems !== undefined || filters.maxActionItems !== undefined,
    filters.minParticipants !== undefined || filters.maxParticipants !== undefined,
    // ADR-041: Access issues filter
    filters.hasAccessIssues !== undefined,
    // ADR-073: Private channels filter
    filters.containsPrivateChannels !== undefined,
  ].filter(Boolean).length;

  const handleClearFilters = () => {
    setSearchInput("");  // Clear local search state
    onFiltersChange({
      ...filters,
      searchQuery: undefined,
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
      // ADR-021: Clear content count filters
      minKeyPoints: undefined,
      maxKeyPoints: undefined,
      minActionItems: undefined,
      maxActionItems: undefined,
      minParticipants: undefined,
      maxParticipants: undefined,
      // ADR-041: Clear access issues filter
      hasAccessIssues: undefined,
      // ADR-073: Clear private channels filter
      containsPrivateChannels: undefined,
    });
  };

  return (
    <div className="space-y-3">
      {/* Main filter row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Text search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search title, content..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onBlur={handleSearchCommit}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                handleSearchCommit();
              }
            }}
            className="h-8 w-[200px] pl-8"
          />
        </div>

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

        {/* ADR-026: Platform filter */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Platform:</span>
          <Select
            value={filters.platform || "all"}
            onValueChange={(v) => onFiltersChange({ ...filters, platform: v === "all" ? undefined : v })}
          >
            <SelectTrigger className="w-[130px] h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Platforms</SelectItem>
              <SelectItem value="discord">Discord</SelectItem>
              <SelectItem value="slack">Slack</SelectItem>
              <SelectItem value="whatsapp">WhatsApp</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* ADR-035: Summary Length filter */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Length:</span>
          <Select
            value={filters.summaryLength || "all"}
            onValueChange={(v) => onFiltersChange({ ...filters, summaryLength: v === "all" ? undefined : v })}
          >
            <SelectTrigger className="w-[130px] h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Lengths</SelectItem>
              <SelectItem value="brief">Brief</SelectItem>
              <SelectItem value="detailed">Detailed</SelectItem>
              <SelectItem value="comprehensive">Comprehensive</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* ADR-035: Perspective filter - dynamic from system + custom */}
        {perspectives.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Perspective:</span>
            <Select
              value={filters.perspective || (filters.excludeCustomPerspectives !== false ? "standard" : "all")}
              onValueChange={(v) => {
                if (v === "standard") {
                  // Standard Perspectives = exclude custom, no specific perspective filter
                  onFiltersChange({ ...filters, perspective: undefined, excludeCustomPerspectives: true });
                } else if (v === "all") {
                  // All Perspectives = include custom, no specific perspective filter
                  onFiltersChange({ ...filters, perspective: undefined, excludeCustomPerspectives: false });
                } else {
                  // Specific perspective selected
                  onFiltersChange({ ...filters, perspective: v, excludeCustomPerspectives: undefined });
                }
              }}
            >
              <SelectTrigger className="w-[160px] h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="standard">Standard Perspectives</SelectItem>
                {customPerspectives.length > 0 && (
                  <SelectItem value="all">All Perspectives</SelectItem>
                )}
                <div className="h-px bg-border my-1" />
                {standardPerspectives.map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    {p.label}
                  </SelectItem>
                ))}
                {customPerspectives.length > 0 && (
                  <>
                    <div className="h-px bg-border my-1" />
                    <div className="px-2 py-1 text-xs text-muted-foreground">Custom</div>
                    {customPerspectives.map((p) => (
                      <SelectItem key={p.value} value={p.value}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </>
                )}
              </SelectContent>
            </Select>
          </div>
        )}

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
          <PopoverContent className="w-auto min-w-[600px] p-0" align="start">
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

              {/* ADR-041: Access issues filter */}
              <div className="space-y-2">
                <label className="text-sm text-muted-foreground">Channel Access</label>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant={filters.hasAccessIssues === false ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      onFiltersChange({
                        ...filters,
                        hasAccessIssues: filters.hasAccessIssues === false ? undefined : false,
                      })
                    }
                  >
                    <CheckCircle2 className="mr-1 h-3 w-3" />
                    Full Access
                  </Button>
                  <Button
                    variant={filters.hasAccessIssues === true ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      onFiltersChange({
                        ...filters,
                        hasAccessIssues: filters.hasAccessIssues === true ? undefined : true,
                      })
                    }
                  >
                    <AlertTriangle className="mr-1 h-3 w-3" />
                    Partial Access
                  </Button>
                </div>
              </div>

              {/* ADR-073: Private channels filter */}
              <div className="space-y-2">
                <label className="text-sm text-muted-foreground">Channel Privacy</label>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant={filters.containsPrivateChannels === false ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      onFiltersChange({
                        ...filters,
                        containsPrivateChannels: filters.containsPrivateChannels === false ? undefined : false,
                      })
                    }
                  >
                    Public Only
                  </Button>
                  <Button
                    variant={filters.containsPrivateChannels === true ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      onFiltersChange({
                        ...filters,
                        containsPrivateChannels: filters.containsPrivateChannels === true ? undefined : true,
                      })
                    }
                    className={filters.containsPrivateChannels === true ? "bg-red-600 hover:bg-red-700" : ""}
                  >
                    <Lock className="mr-1 h-3 w-3" />
                    Private Channels
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
                  <DebouncedNumberInput
                    placeholder="Min"
                    className="w-20 h-8"
                    min={0}
                    value={filters.minMessageCount}
                    onChange={(val) =>
                      onFiltersChange({
                        ...filters,
                        minMessageCount: val,
                      })
                    }
                  />
                  <span className="text-muted-foreground">to</span>
                  <DebouncedNumberInput
                    placeholder="Max"
                    className="w-20 h-8"
                    min={0}
                    value={filters.maxMessageCount}
                    onChange={(val) =>
                      onFiltersChange({
                        ...filters,
                        maxMessageCount: val,
                      })
                    }
                  />
                </div>
              </div>

              {/* ADR-021: Content count filters */}
              <div className="space-y-3 border-t pt-3">
                <label className="text-sm text-muted-foreground">Content Counts</label>

                {/* Key Points count */}
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Key Points</label>
                  <div className="flex items-center gap-2">
                    <DebouncedNumberInput
                      placeholder="Min"
                      className="w-16 h-7 text-xs"
                      min={0}
                      value={filters.minKeyPoints}
                      onChange={(val) =>
                        onFiltersChange({
                          ...filters,
                          minKeyPoints: val,
                        })
                      }
                    />
                    <span className="text-xs text-muted-foreground">-</span>
                    <DebouncedNumberInput
                      placeholder="Max"
                      className="w-16 h-7 text-xs"
                      min={0}
                      value={filters.maxKeyPoints}
                      onChange={(val) =>
                        onFiltersChange({
                          ...filters,
                          maxKeyPoints: val,
                        })
                      }
                    />
                  </div>
                </div>

                {/* Action Items count */}
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Action Items</label>
                  <div className="flex items-center gap-2">
                    <DebouncedNumberInput
                      placeholder="Min"
                      className="w-16 h-7 text-xs"
                      min={0}
                      value={filters.minActionItems}
                      onChange={(val) =>
                        onFiltersChange({
                          ...filters,
                          minActionItems: val,
                        })
                      }
                    />
                    <span className="text-xs text-muted-foreground">-</span>
                    <DebouncedNumberInput
                      placeholder="Max"
                      className="w-16 h-7 text-xs"
                      min={0}
                      value={filters.maxActionItems}
                      onChange={(val) =>
                        onFiltersChange({
                          ...filters,
                          maxActionItems: val,
                        })
                      }
                    />
                  </div>
                </div>

                {/* Participants count */}
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Participants</label>
                  <div className="flex items-center gap-2">
                    <DebouncedNumberInput
                      placeholder="Min"
                      className="w-16 h-7 text-xs"
                      min={0}
                      value={filters.minParticipants}
                      onChange={(val) =>
                        onFiltersChange({
                          ...filters,
                          minParticipants: val,
                        })
                      }
                    />
                    <span className="text-xs text-muted-foreground">-</span>
                    <DebouncedNumberInput
                      placeholder="Max"
                      className="w-16 h-7 text-xs"
                      min={0}
                      value={filters.maxParticipants}
                      onChange={(val) =>
                        onFiltersChange({
                          ...filters,
                          maxParticipants: val,
                        })
                      }
                    />
                  </div>
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
          {filters.archivePeriod && (
            <Badge variant="default" className="gap-1">
              <CalendarIcon className="h-3 w-3 mr-1" />
              {/* Parse as local date to avoid timezone offset issues */}
              {format(parse(filters.archivePeriod, "yyyy-MM-dd", new Date()), "MMM d, yyyy")}
              <button
                onClick={() => onFiltersChange({ ...filters, archivePeriod: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
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
          {/* ADR-021: Content count filter badges */}
          {(filters.minKeyPoints !== undefined || filters.maxKeyPoints !== undefined) && (
            <Badge variant="secondary" className="gap-1">
              Key Points: {filters.minKeyPoints ?? 0} - {filters.maxKeyPoints ?? "∞"}
              <button
                onClick={() => onFiltersChange({ ...filters, minKeyPoints: undefined, maxKeyPoints: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {(filters.minActionItems !== undefined || filters.maxActionItems !== undefined) && (
            <Badge variant="secondary" className="gap-1">
              Action Items: {filters.minActionItems ?? 0} - {filters.maxActionItems ?? "∞"}
              <button
                onClick={() => onFiltersChange({ ...filters, minActionItems: undefined, maxActionItems: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {(filters.minParticipants !== undefined || filters.maxParticipants !== undefined) && (
            <Badge variant="secondary" className="gap-1">
              Participants: {filters.minParticipants ?? 0} - {filters.maxParticipants ?? "∞"}
              <button
                onClick={() => onFiltersChange({ ...filters, minParticipants: undefined, maxParticipants: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {/* ADR-035: Summary length filter badge */}
          {filters.summaryLength && (
            <Badge variant="secondary" className="gap-1">
              Length: {filters.summaryLength}
              <button
                onClick={() => onFiltersChange({ ...filters, summaryLength: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {/* ADR-035: Perspective filter badge */}
          {filters.perspective && (
            <Badge variant="secondary" className="gap-1">
              Perspective: {filters.perspective}
              <button
                onClick={() => onFiltersChange({ ...filters, perspective: undefined, excludeCustomPerspectives: true })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {filters.excludeCustomPerspectives === false && (
            <Badge variant="secondary" className="gap-1">
              Including custom perspectives
              <button
                onClick={() => onFiltersChange({ ...filters, excludeCustomPerspectives: true })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {/* ADR-041: Access issues filter badge */}
          {filters.hasAccessIssues !== undefined && (
            <Badge variant="secondary" className="gap-1">
              {filters.hasAccessIssues ? "Partial Access" : "Full Access"}
              <button
                onClick={() => onFiltersChange({ ...filters, hasAccessIssues: undefined })}
                className="ml-1 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
          {/* ADR-073: Private channels filter badge */}
          {filters.containsPrivateChannels !== undefined && (
            <Badge
              variant={filters.containsPrivateChannels ? "destructive" : "secondary"}
              className="gap-1"
            >
              <Lock className="h-3 w-3" />
              {filters.containsPrivateChannels ? "Private Channels" : "Public Only"}
              <button
                onClick={() => onFiltersChange({ ...filters, containsPrivateChannels: undefined })}
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
