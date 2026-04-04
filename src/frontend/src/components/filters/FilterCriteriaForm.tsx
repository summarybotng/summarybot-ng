/**
 * Filter Criteria Form Component (ADR-037)
 *
 * Compact form for selecting filter criteria.
 * Used in feed creation, webhook filtering, and anywhere filters need to be configured.
 */

import { useState } from "react";
import { format } from "date-fns";
import {
  Calendar as CalendarIcon,
  Filter,
  Hash,
  CheckCircle2,
  AlertTriangle,
  ListChecks,
  Users,
  MessageSquare,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
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
import type { SummaryFilterCriteria, SummarySourceType, ChannelModeType } from "@/types/filters";
import { DebouncedNumberInput } from "./DebouncedNumberInput";
import { DateRangeSelector } from "./DateRangeSelector";
import type { Channel } from "@/types";

/** Perspective option for dynamic dropdown */
export interface PerspectiveOption {
  value: string;
  label: string;
  isCustom?: boolean;
}

interface FilterCriteriaFormProps {
  criteria: SummaryFilterCriteria;
  onChange: (criteria: SummaryFilterCriteria) => void;
  /** Available channels for channel filter */
  channels?: Channel[];
  /** Available perspectives (system + custom) */
  perspectives?: PerspectiveOption[];
  /** Show sort options */
  showSortOptions?: boolean;
  /** Compact layout for dialogs */
  compact?: boolean;
  /** Label for the filters section */
  label?: string;
}

export function FilterCriteriaForm({
  criteria,
  onChange,
  channels = [],
  perspectives = [],
  showSortOptions = false,
  compact = false,
  label = "Filter Criteria",
}: FilterCriteriaFormProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [dateRangeOpen, setDateRangeOpen] = useState(false);

  const updateCriteria = (updates: Partial<SummaryFilterCriteria>) => {
    onChange({ ...criteria, ...updates });
  };

  return (
    <div className="space-y-4">
      {label && (
        <div className="flex items-center gap-2 text-sm font-medium">
          <Filter className="h-4 w-4" />
          {label}
        </div>
      )}

      {/* Primary filters row */}
      <div className={`flex flex-wrap gap-3 ${compact ? "gap-2" : ""}`}>
        {/* Source filter */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Source:</span>
          <Select
            value={criteria.source || "all"}
            onValueChange={(v) => updateCriteria({ source: v as SummarySourceType })}
          >
            <SelectTrigger className={compact ? "w-[110px] h-8" : "w-[130px] h-8"}>
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

        {/* Channel filter */}
        {channels.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Channel:</span>
            <Select
              value={criteria.channelIds?.[0] || "all"}
              onValueChange={(v) =>
                updateCriteria({
                  channelIds: v === "all" ? undefined : [v],
                  channelMode: v === "all" ? "all" : "single",
                })
              }
            >
              <SelectTrigger className={compact ? "w-[140px] h-8" : "w-[160px] h-8"}>
                <SelectValue placeholder="All Channels" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Channels</SelectItem>
                {channels
                  .filter((c) => c.type === "text")
                  .map((channel) => (
                    <SelectItem key={channel.id} value={channel.id}>
                      #{channel.name}
                    </SelectItem>
                  ))}
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
                (criteria.createdAfter || criteria.createdBefore) && "border-primary"
              )}
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {criteria.createdAfter || criteria.createdBefore ? (
                <span>
                  {criteria.createdAfter && format(new Date(criteria.createdAfter), "MMM d")}
                  {criteria.createdAfter && criteria.createdBefore && " - "}
                  {criteria.createdBefore && format(new Date(criteria.createdBefore), "MMM d")}
                </span>
              ) : (
                <span>Date Range</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto min-w-[600px] p-0" align="start">
            <DateRangeSelector
              from={criteria.createdAfter ? new Date(criteria.createdAfter) : undefined}
              to={criteria.createdBefore ? new Date(criteria.createdBefore) : undefined}
              onSelect={(from, to) => {
                updateCriteria({
                  createdAfter: from?.toISOString(),
                  createdBefore: to?.toISOString(),
                });
              }}
              onClear={() => {
                updateCriteria({
                  createdAfter: undefined,
                  createdBefore: undefined,
                });
                setDateRangeOpen(false);
              }}
            />
          </PopoverContent>
        </Popover>
      </div>

      {/* Content flags */}
      <div className="space-y-2">
        <label className="text-sm text-muted-foreground flex items-center gap-2">
          <ListChecks className="h-3 w-3" />
          Content Requirements
        </label>
        <div className="flex flex-wrap gap-2">
          <Button
            variant={criteria.hasGrounding === true ? "default" : "outline"}
            size="sm"
            onClick={() =>
              updateCriteria({
                hasGrounding: criteria.hasGrounding === true ? undefined : true,
              })
            }
          >
            <CheckCircle2 className="mr-1 h-3 w-3" />
            With Grounding
          </Button>
          <Button
            variant={criteria.hasKeyPoints === true ? "default" : "outline"}
            size="sm"
            onClick={() =>
              updateCriteria({
                hasKeyPoints: criteria.hasKeyPoints === true ? undefined : true,
              })
            }
          >
            Key Points
          </Button>
          <Button
            variant={criteria.hasActionItems === true ? "default" : "outline"}
            size="sm"
            onClick={() =>
              updateCriteria({
                hasActionItems: criteria.hasActionItems === true ? undefined : true,
              })
            }
          >
            Action Items
          </Button>
          <Button
            variant={criteria.hasParticipants === true ? "default" : "outline"}
            size="sm"
            onClick={() =>
              updateCriteria({
                hasParticipants: criteria.hasParticipants === true ? undefined : true,
              })
            }
          >
            <Users className="mr-1 h-3 w-3" />
            Participants
          </Button>
        </div>
      </div>

      {/* Advanced filters toggle */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="w-full justify-between"
      >
        <span>Advanced Filters</span>
        {showAdvanced ? (
          <ChevronUp className="h-4 w-4" />
        ) : (
          <ChevronDown className="h-4 w-4" />
        )}
      </Button>

      {/* Advanced filters */}
      {showAdvanced && (
        <div className="space-y-4 border-t pt-4">
          {/* Platform and generation settings */}
          <div className="flex flex-wrap gap-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Platform:</span>
              <Select
                value={criteria.platform || "all"}
                onValueChange={(v) => updateCriteria({ platform: v === "all" ? undefined : v })}
              >
                <SelectTrigger className="w-[120px] h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="discord">Discord</SelectItem>
                  <SelectItem value="whatsapp">WhatsApp</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Length:</span>
              <Select
                value={criteria.summaryLength || "all"}
                onValueChange={(v) => updateCriteria({ summaryLength: v === "all" ? undefined : v })}
              >
                <SelectTrigger className="w-[120px] h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="brief">Brief</SelectItem>
                  <SelectItem value="detailed">Detailed</SelectItem>
                  <SelectItem value="comprehensive">Comprehensive</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {perspectives.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Perspective:</span>
                <Select
                  value={criteria.perspective || "all"}
                  onValueChange={(v) => updateCriteria({ perspective: v === "all" ? undefined : v })}
                >
                  <SelectTrigger className="w-[140px] h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {perspectives.map((p) => (
                      <SelectItem key={p.value} value={p.value}>
                        {p.label}{p.isCustom ? " *" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* Channel mode */}
          {channels.length === 0 && (
            <div className="space-y-2">
              <label className="text-sm text-muted-foreground flex items-center gap-2">
                <Hash className="h-3 w-3" />
                Channel Mode
              </label>
              <Select
                value={criteria.channelMode || "all"}
                onValueChange={(v) => updateCriteria({ channelMode: v as ChannelModeType })}
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
          )}

          {/* Count filters */}
          <div className="space-y-3">
            <label className="text-sm text-muted-foreground">Count Ranges</label>

            {/* Message count */}
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm w-24">Messages:</span>
              <DebouncedNumberInput
                placeholder="Min"
                className="w-20 h-8"
                min={0}
                value={criteria.minMessageCount}
                onChange={(val) => updateCriteria({ minMessageCount: val })}
              />
              <span className="text-muted-foreground">to</span>
              <DebouncedNumberInput
                placeholder="Max"
                className="w-20 h-8"
                min={0}
                value={criteria.maxMessageCount}
                onChange={(val) => updateCriteria({ maxMessageCount: val })}
              />
            </div>

            {/* Key points count */}
            <div className="flex items-center gap-2">
              <ListChecks className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm w-24">Key Points:</span>
              <DebouncedNumberInput
                placeholder="Min"
                className="w-20 h-8"
                min={0}
                value={criteria.minKeyPoints}
                onChange={(val) => updateCriteria({ minKeyPoints: val })}
              />
              <span className="text-muted-foreground">to</span>
              <DebouncedNumberInput
                placeholder="Max"
                className="w-20 h-8"
                min={0}
                value={criteria.maxKeyPoints}
                onChange={(val) => updateCriteria({ maxKeyPoints: val })}
              />
            </div>

            {/* Action items count */}
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm w-24">Actions:</span>
              <DebouncedNumberInput
                placeholder="Min"
                className="w-20 h-8"
                min={0}
                value={criteria.minActionItems}
                onChange={(val) => updateCriteria({ minActionItems: val })}
              />
              <span className="text-muted-foreground">to</span>
              <DebouncedNumberInput
                placeholder="Max"
                className="w-20 h-8"
                min={0}
                value={criteria.maxActionItems}
                onChange={(val) => updateCriteria({ maxActionItems: val })}
              />
            </div>

            {/* Participants count */}
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm w-24">Participants:</span>
              <DebouncedNumberInput
                placeholder="Min"
                className="w-20 h-8"
                min={0}
                value={criteria.minParticipants}
                onChange={(val) => updateCriteria({ minParticipants: val })}
              />
              <span className="text-muted-foreground">to</span>
              <DebouncedNumberInput
                placeholder="Max"
                className="w-20 h-8"
                min={0}
                value={criteria.maxParticipants}
                onChange={(val) => updateCriteria({ maxParticipants: val })}
              />
            </div>
          </div>
        </div>
      )}

      {/* Sort options */}
      {showSortOptions && (
        <div className="flex items-center gap-3 border-t pt-4">
          <span className="text-sm text-muted-foreground">Sort by:</span>
          <Select
            value={criteria.sortBy || "created_at"}
            onValueChange={(v) => updateCriteria({ sortBy: v as SummaryFilterCriteria["sortBy"] })}
          >
            <SelectTrigger className="w-[140px] h-8">
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
              updateCriteria({
                sortOrder: criteria.sortOrder === "desc" ? "asc" : "desc",
              })
            }
          >
            {criteria.sortOrder === "desc" ? "↓" : "↑"}
          </Button>
        </div>
      )}
    </div>
  );
}
