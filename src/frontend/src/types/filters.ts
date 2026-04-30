/**
 * Centralized Summary Filter Criteria (ADR-037)
 *
 * Single source of truth for filtering summaries across:
 * - Summary list view
 * - Bulk operations
 * - Feeds (RSS/Atom)
 * - Webhooks (future)
 * - Email digests (future)
 */

// Source types
export type SummarySourceType = "realtime" | "scheduled" | "manual" | "archive" | "imported" | "all";

// Channel mode types
export type ChannelModeType = "single" | "multi" | "all";

// Sort options
export type SortByType = "created_at" | "message_count" | "archive_period";
export type SortOrderType = "asc" | "desc";

/**
 * Comprehensive filter criteria for summaries.
 * Used by summary lists, feeds, bulk operations, and future features.
 */
export interface SummaryFilterCriteria {
  // === Text Search ===
  /** Full-text search query (searches title, summary text, key points, action items) */
  searchQuery?: string;

  // === Source Filtering ===
  /** Filter by summary source type */
  source?: SummarySourceType;
  /** Show archived summaries */
  archived?: boolean;

  // === Time Filtering ===
  /** Filter summaries created after this date (ISO string) */
  createdAfter?: string;
  /** Filter summaries created before this date (ISO string) */
  createdBefore?: string;
  /** Filter by archive period (YYYY-MM-DD format) */
  archivePeriod?: string;

  // === Channel Filtering ===
  /** Filter by channel mode */
  channelMode?: ChannelModeType;
  /** Filter by specific channel IDs */
  channelIds?: string[];

  // === Content Flags ===
  /** Has grounded references */
  hasGrounding?: boolean;
  /** Has key points */
  hasKeyPoints?: boolean;
  /** Has action items */
  hasActionItems?: boolean;
  /** Has participants listed */
  hasParticipants?: boolean;

  // === Content Counts ===
  minMessageCount?: number;
  maxMessageCount?: number;
  minKeyPoints?: number;
  maxKeyPoints?: number;
  minActionItems?: number;
  maxActionItems?: number;
  minParticipants?: number;
  maxParticipants?: number;

  // === Generation Settings ===
  /** Filter by platform (discord, whatsapp, etc.) */
  platform?: string;
  /** Filter by summary length (brief, detailed, comprehensive) */
  summaryLength?: string;
  /** Filter by perspective (general, developer, marketing, etc.) */
  perspective?: string;
  /** Exclude summaries with custom prompt templates */
  excludeCustomPerspectives?: boolean;

  // === Access Issues (ADR-041) ===
  /** Filter by channel access issues (true = partial access, false = full access) */
  hasAccessIssues?: boolean;

  // === Private Channels (ADR-073) ===
  /** Filter by private/locked channel content (true = contains private content) */
  containsPrivateChannels?: boolean;

  // === Sorting (for list views, not feeds) ===
  sortBy?: SortByType;
  sortOrder?: SortOrderType;
}

/**
 * Convert SummaryFilterCriteria to URL search params for API calls.
 */
export function criteriaToSearchParams(criteria: SummaryFilterCriteria): URLSearchParams {
  const params = new URLSearchParams();

  // Text search
  if (criteria.searchQuery) {
    params.set("q", criteria.searchQuery);
  }

  // Source filtering
  if (criteria.source && criteria.source !== "all") {
    params.set("source", criteria.source);
  }
  if (criteria.archived !== undefined) {
    params.set("archived", criteria.archived.toString());
  }

  // Time filtering
  if (criteria.createdAfter) params.set("created_after", criteria.createdAfter);
  if (criteria.createdBefore) params.set("created_before", criteria.createdBefore);
  if (criteria.archivePeriod) params.set("archive_period", criteria.archivePeriod);

  // Channel filtering
  if (criteria.channelMode && criteria.channelMode !== "all") {
    params.set("channel_mode", criteria.channelMode);
  }
  if (criteria.channelIds?.length) {
    params.set("channel_ids", criteria.channelIds.join(","));
  }

  // Content flags
  if (criteria.hasGrounding !== undefined) {
    params.set("has_grounding", criteria.hasGrounding.toString());
  }
  if (criteria.hasKeyPoints !== undefined) {
    params.set("has_key_points", criteria.hasKeyPoints.toString());
  }
  if (criteria.hasActionItems !== undefined) {
    params.set("has_action_items", criteria.hasActionItems.toString());
  }
  if (criteria.hasParticipants !== undefined) {
    params.set("has_participants", criteria.hasParticipants.toString());
  }

  // Content counts
  if (criteria.minMessageCount !== undefined) {
    params.set("min_message_count", criteria.minMessageCount.toString());
  }
  if (criteria.maxMessageCount !== undefined) {
    params.set("max_message_count", criteria.maxMessageCount.toString());
  }
  if (criteria.minKeyPoints !== undefined) {
    params.set("min_key_points", criteria.minKeyPoints.toString());
  }
  if (criteria.maxKeyPoints !== undefined) {
    params.set("max_key_points", criteria.maxKeyPoints.toString());
  }
  if (criteria.minActionItems !== undefined) {
    params.set("min_action_items", criteria.minActionItems.toString());
  }
  if (criteria.maxActionItems !== undefined) {
    params.set("max_action_items", criteria.maxActionItems.toString());
  }
  if (criteria.minParticipants !== undefined) {
    params.set("min_participants", criteria.minParticipants.toString());
  }
  if (criteria.maxParticipants !== undefined) {
    params.set("max_participants", criteria.maxParticipants.toString());
  }

  // Generation settings
  if (criteria.platform) params.set("platform", criteria.platform);
  if (criteria.summaryLength) params.set("summary_length", criteria.summaryLength);
  if (criteria.perspective) params.set("perspective", criteria.perspective);
  if (criteria.excludeCustomPerspectives) params.set("exclude_custom_perspectives", "true");

  // ADR-041: Access issues filter
  if (criteria.hasAccessIssues !== undefined) {
    params.set("has_access_issues", criteria.hasAccessIssues.toString());
  }

  // ADR-073: Private channels filter
  if (criteria.containsPrivateChannels !== undefined) {
    params.set("contains_private_channels", criteria.containsPrivateChannels.toString());
  }

  // Sorting
  if (criteria.sortBy) params.set("sort_by", criteria.sortBy);
  if (criteria.sortOrder) params.set("sort_order", criteria.sortOrder);

  return params;
}

/**
 * Convert SummaryFilterCriteria to API request body format (snake_case).
 * Used for bulk operations and feed criteria.
 */
export function criteriaToApiBody(criteria: SummaryFilterCriteria): Record<string, unknown> {
  const body: Record<string, unknown> = {};

  if (criteria.source && criteria.source !== "all") body.source = criteria.source;
  if (criteria.archived !== undefined) body.archived = criteria.archived;
  if (criteria.createdAfter) body.created_after = criteria.createdAfter;
  if (criteria.createdBefore) body.created_before = criteria.createdBefore;
  if (criteria.archivePeriod) body.archive_period = criteria.archivePeriod;
  if (criteria.channelMode && criteria.channelMode !== "all") body.channel_mode = criteria.channelMode;
  if (criteria.channelIds?.length) body.channel_ids = criteria.channelIds;
  if (criteria.hasGrounding !== undefined) body.has_grounding = criteria.hasGrounding;
  if (criteria.hasKeyPoints !== undefined) body.has_key_points = criteria.hasKeyPoints;
  if (criteria.hasActionItems !== undefined) body.has_action_items = criteria.hasActionItems;
  if (criteria.hasParticipants !== undefined) body.has_participants = criteria.hasParticipants;
  if (criteria.minMessageCount !== undefined) body.min_message_count = criteria.minMessageCount;
  if (criteria.maxMessageCount !== undefined) body.max_message_count = criteria.maxMessageCount;
  if (criteria.minKeyPoints !== undefined) body.min_key_points = criteria.minKeyPoints;
  if (criteria.maxKeyPoints !== undefined) body.max_key_points = criteria.maxKeyPoints;
  if (criteria.minActionItems !== undefined) body.min_action_items = criteria.minActionItems;
  if (criteria.maxActionItems !== undefined) body.max_action_items = criteria.maxActionItems;
  if (criteria.minParticipants !== undefined) body.min_participants = criteria.minParticipants;
  if (criteria.maxParticipants !== undefined) body.max_participants = criteria.maxParticipants;
  if (criteria.platform) body.platform = criteria.platform;
  if (criteria.summaryLength) body.summary_length = criteria.summaryLength;
  if (criteria.perspective) body.perspective = criteria.perspective;
  // ADR-041: Access issues filter
  if (criteria.hasAccessIssues !== undefined) body.has_access_issues = criteria.hasAccessIssues;
  // ADR-073: Private channels filter
  if (criteria.containsPrivateChannels !== undefined) body.contains_private_channels = criteria.containsPrivateChannels;

  return body;
}

/**
 * Count active filters in criteria (excluding sort options).
 */
export function countActiveFilters(criteria: SummaryFilterCriteria): number {
  return [
    criteria.searchQuery,
    criteria.source && criteria.source !== "all",
    criteria.archived === true,
    criteria.createdAfter,
    criteria.createdBefore,
    criteria.archivePeriod,
    criteria.channelMode && criteria.channelMode !== "all",
    criteria.channelIds?.length,
    criteria.hasGrounding !== undefined,
    criteria.hasKeyPoints !== undefined,
    criteria.hasActionItems !== undefined,
    criteria.hasParticipants !== undefined,
    criteria.minMessageCount !== undefined || criteria.maxMessageCount !== undefined,
    criteria.minKeyPoints !== undefined || criteria.maxKeyPoints !== undefined,
    criteria.minActionItems !== undefined || criteria.maxActionItems !== undefined,
    criteria.minParticipants !== undefined || criteria.maxParticipants !== undefined,
    criteria.platform,
    criteria.summaryLength,
    criteria.perspective,
    criteria.hasAccessIssues !== undefined,
  ].filter(Boolean).length;
}

/**
 * Get default/empty filter criteria.
 */
export function getDefaultCriteria(): SummaryFilterCriteria {
  return {
    source: "all",
    archived: false,
    channelMode: "all",
    sortBy: "created_at",
    sortOrder: "desc",
  };
}

/**
 * Clear all filters except sort options.
 */
export function clearFilters(criteria: SummaryFilterCriteria): SummaryFilterCriteria {
  return {
    source: "all",
    archived: false,
    channelMode: "all",
    sortBy: criteria.sortBy,
    sortOrder: criteria.sortOrder,
  };
}

/**
 * API response format for criteria (snake_case from backend).
 */
export interface ApiCriteria {
  source?: string;
  archived?: boolean;
  created_after?: string;
  created_before?: string;
  archive_period?: string;
  channel_mode?: string;
  channel_ids?: string[];
  has_grounding?: boolean;
  has_key_points?: boolean;
  has_action_items?: boolean;
  has_participants?: boolean;
  min_message_count?: number;
  max_message_count?: number;
  min_key_points?: number;
  max_key_points?: number;
  min_action_items?: number;
  max_action_items?: number;
  min_participants?: number;
  max_participants?: number;
  platform?: string;
  summary_length?: string;
  perspective?: string;
  has_access_issues?: boolean;
}

/**
 * Convert API criteria (snake_case) to frontend criteria (camelCase).
 */
export function apiCriteriaToFrontend(api: ApiCriteria | null | undefined): SummaryFilterCriteria {
  // Defensive: ensure api is a proper object
  if (!api || typeof api !== 'object' || Array.isArray(api)) {
    console.warn('[apiCriteriaToFrontend] Invalid criteria input:', api);
    return {};
  }
  return {
    source: api.source as SummarySourceType | undefined,
    archived: api.archived,
    createdAfter: api.created_after,
    createdBefore: api.created_before,
    archivePeriod: api.archive_period,
    channelMode: api.channel_mode as ChannelModeType | undefined,
    channelIds: api.channel_ids,
    hasGrounding: api.has_grounding,
    hasKeyPoints: api.has_key_points,
    hasActionItems: api.has_action_items,
    hasParticipants: api.has_participants,
    minMessageCount: api.min_message_count,
    maxMessageCount: api.max_message_count,
    minKeyPoints: api.min_key_points,
    maxKeyPoints: api.max_key_points,
    minActionItems: api.min_action_items,
    maxActionItems: api.max_action_items,
    minParticipants: api.min_participants,
    maxParticipants: api.max_participants,
    platform: api.platform,
    summaryLength: api.summary_length,
    perspective: api.perspective,
    hasAccessIssues: api.has_access_issues,
  };
}
