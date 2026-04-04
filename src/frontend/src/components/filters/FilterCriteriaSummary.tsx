/**
 * Filter Criteria Summary Component (ADR-037)
 *
 * Compact display of active filters as removable badges.
 * Used to show and manage active filters in feeds, webhooks, and list views.
 */

import { format, parse } from "date-fns";

// Debug: verify date-fns functions are loaded
if (typeof parse !== 'function') {
  console.error('date-fns parse is not a function:', typeof parse, parse);
}
if (typeof format !== 'function') {
  console.error('date-fns format is not a function:', typeof format, format);
}
import { X, Calendar as CalendarIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { SummaryFilterCriteria } from "@/types/filters";

interface FilterCriteriaSummaryProps {
  criteria: SummaryFilterCriteria;
  onUpdate: (criteria: Partial<SummaryFilterCriteria>) => void;
  /** Show as compact badges for small spaces */
  compact?: boolean;
}

export function FilterCriteriaSummary({
  criteria,
  onUpdate,
  compact = false,
}: FilterCriteriaSummaryProps) {
  // Debug logging
  console.log('[FilterCriteriaSummary] criteria:', criteria);
  console.log('[FilterCriteriaSummary] typeof criteria:', typeof criteria);
  console.log('[FilterCriteriaSummary] onUpdate:', typeof onUpdate);

  const filters: Array<{
    key: string;
    label: string;
    icon?: React.ReactNode;
    onRemove: () => void;
  }> = [];

  // Source filter
  if (criteria.source && criteria.source !== "all") {
    filters.push({
      key: "source",
      label: `Source: ${criteria.source}`,
      onRemove: () => onUpdate({ source: "all" }),
    });
  }

  // Archived
  if (criteria.archived === true) {
    filters.push({
      key: "archived",
      label: "Archived",
      onRemove: () => onUpdate({ archived: false }),
    });
  }

  // Archive period
  if (criteria.archivePeriod) {
    let archiveLabel = criteria.archivePeriod;
    try {
      const parsed = parse(criteria.archivePeriod, "yyyy-MM-dd", new Date());
      archiveLabel = format(parsed, "MMM d, yyyy");
    } catch (e) {
      console.error("Failed to parse archivePeriod:", criteria.archivePeriod, e);
    }
    filters.push({
      key: "archivePeriod",
      label: archiveLabel,
      icon: <CalendarIcon className="h-3 w-3 mr-1" />,
      onRemove: () => onUpdate({ archivePeriod: undefined }),
    });
  }

  // Date range
  if (criteria.createdAfter) {
    filters.push({
      key: "createdAfter",
      label: `After: ${format(new Date(criteria.createdAfter), "MMM d, yyyy")}`,
      onRemove: () => onUpdate({ createdAfter: undefined }),
    });
  }
  if (criteria.createdBefore) {
    filters.push({
      key: "createdBefore",
      label: `Before: ${format(new Date(criteria.createdBefore), "MMM d, yyyy")}`,
      onRemove: () => onUpdate({ createdBefore: undefined }),
    });
  }

  // Channel mode
  if (criteria.channelMode && criteria.channelMode !== "all") {
    filters.push({
      key: "channelMode",
      label: criteria.channelMode === "single" ? "Single Channel" : "Multi-Channel",
      onRemove: () => onUpdate({ channelMode: "all" }),
    });
  }

  // Channel IDs
  if (criteria.channelIds?.length) {
    filters.push({
      key: "channelIds",
      label: `${criteria.channelIds.length} channel${criteria.channelIds.length > 1 ? "s" : ""}`,
      onRemove: () => onUpdate({ channelIds: undefined }),
    });
  }

  // Content flags
  if (criteria.hasGrounding !== undefined) {
    filters.push({
      key: "hasGrounding",
      label: criteria.hasGrounding ? "With Grounding" : "No Grounding",
      onRemove: () => onUpdate({ hasGrounding: undefined }),
    });
  }
  if (criteria.hasKeyPoints === true) {
    filters.push({
      key: "hasKeyPoints",
      label: "Has Key Points",
      onRemove: () => onUpdate({ hasKeyPoints: undefined }),
    });
  }
  if (criteria.hasActionItems === true) {
    filters.push({
      key: "hasActionItems",
      label: "Has Action Items",
      onRemove: () => onUpdate({ hasActionItems: undefined }),
    });
  }
  if (criteria.hasParticipants === true) {
    filters.push({
      key: "hasParticipants",
      label: "Has Participants",
      onRemove: () => onUpdate({ hasParticipants: undefined }),
    });
  }

  // Message count range
  if (criteria.minMessageCount !== undefined || criteria.maxMessageCount !== undefined) {
    filters.push({
      key: "messageCount",
      label: `Messages: ${criteria.minMessageCount ?? 0} - ${criteria.maxMessageCount ?? "∞"}`,
      onRemove: () => onUpdate({ minMessageCount: undefined, maxMessageCount: undefined }),
    });
  }

  // Key points range
  if (criteria.minKeyPoints !== undefined || criteria.maxKeyPoints !== undefined) {
    filters.push({
      key: "keyPointsCount",
      label: `Key Points: ${criteria.minKeyPoints ?? 0} - ${criteria.maxKeyPoints ?? "∞"}`,
      onRemove: () => onUpdate({ minKeyPoints: undefined, maxKeyPoints: undefined }),
    });
  }

  // Action items range
  if (criteria.minActionItems !== undefined || criteria.maxActionItems !== undefined) {
    filters.push({
      key: "actionItemsCount",
      label: `Action Items: ${criteria.minActionItems ?? 0} - ${criteria.maxActionItems ?? "∞"}`,
      onRemove: () => onUpdate({ minActionItems: undefined, maxActionItems: undefined }),
    });
  }

  // Participants range
  if (criteria.minParticipants !== undefined || criteria.maxParticipants !== undefined) {
    filters.push({
      key: "participantsCount",
      label: `Participants: ${criteria.minParticipants ?? 0} - ${criteria.maxParticipants ?? "∞"}`,
      onRemove: () => onUpdate({ minParticipants: undefined, maxParticipants: undefined }),
    });
  }

  // Platform
  if (criteria.platform) {
    filters.push({
      key: "platform",
      label: `Platform: ${criteria.platform}`,
      onRemove: () => onUpdate({ platform: undefined }),
    });
  }

  // Summary length
  if (criteria.summaryLength) {
    filters.push({
      key: "summaryLength",
      label: `Length: ${criteria.summaryLength}`,
      onRemove: () => onUpdate({ summaryLength: undefined }),
    });
  }

  // Perspective
  if (criteria.perspective) {
    filters.push({
      key: "perspective",
      label: `Perspective: ${criteria.perspective}`,
      onRemove: () => onUpdate({ perspective: undefined }),
    });
  }

  if (filters.length === 0) {
    return null;
  }

  return (
    <div className={`flex flex-wrap gap-2 ${compact ? "gap-1" : ""}`}>
      {filters.map((filter) => (
        <Badge
          key={filter.key}
          variant={filter.key === "archivePeriod" ? "default" : "secondary"}
          className={`gap-1 ${compact ? "text-xs" : ""}`}
        >
          {filter.icon}
          {filter.label}
          <button
            onClick={filter.onRemove}
            className="ml-1 hover:text-destructive"
            type="button"
          >
            <X className={`${compact ? "h-2.5 w-2.5" : "h-3 w-3"}`} />
          </button>
        </Badge>
      ))}
    </div>
  );
}
