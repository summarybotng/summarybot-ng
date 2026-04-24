/**
 * Stored Summary Card Component (ADR-005, ADR-008, ADR-009, ADR-018)
 *
 * ADR-008: Extended to show source badges for unified summary experience.
 * ADR-009: Extended to show schedule name with navigation.
 * ADR-018: Extended with selection checkbox for bulk operations.
 */

import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { useTimezone, parseAsUTC, formatRelativeTime } from "@/contexts/TimezoneContext";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Pin,
  MessageSquare,
  Calendar,
  Send,
  Tag,
  History,
  Clock,
  Sparkles,
  Settings2,
  AlertTriangle,
} from "lucide-react";
import { SummaryActions } from "./SummaryActions";
import type { StoredSummary, SummarySourceType } from "@/types";

// ADR-008: Helper to get source badge styling
function getSourceBadge(source: SummarySourceType) {
  switch (source) {
    case "archive":
      return { label: "Archive", className: "bg-orange-500/10 text-orange-600 border-orange-500/30", icon: History };
    case "scheduled":
      return { label: "Scheduled", className: "bg-blue-500/10 text-blue-600 border-blue-500/30", icon: Clock };
    case "manual":
      return { label: "Manual", className: "bg-purple-500/10 text-purple-600 border-purple-500/30", icon: null };
    case "imported":
      return { label: "Imported", className: "bg-green-500/10 text-green-600 border-green-500/30", icon: null };
    case "realtime":
    default:
      return null;  // No badge for realtime (default)
  }
}

// Helper to get platform from archive_source_key (e.g., "slack:123" -> "Slack")
function getPlatformBadge(archiveSourceKey?: string) {
  if (!archiveSourceKey) return null;
  const platform = archiveSourceKey.split(":")[0];
  switch (platform) {
    case "slack":
      return { label: "Slack", className: "bg-purple-500/10 text-purple-600 border-purple-500/30" };
    case "discord":
      return { label: "Discord", className: "bg-indigo-500/10 text-indigo-600 border-indigo-500/30" };
    case "whatsapp":
      return { label: "WhatsApp", className: "bg-green-500/10 text-green-600 border-green-500/30" };
    default:
      return null;
  }
}

interface StoredSummaryCardProps {
  summary: StoredSummary;
  index: number;
  onView: () => void;
  onPush: () => void;
  onPushDM: () => void;  // ADR-047: Push to Discord DM
  onEmail: () => void;  // ADR-030: Email delivery
  onPin: () => void;
  onArchive: () => void;
  onDelete: () => void;
  // ADR-018: Selection support
  isSelected?: boolean;
  onToggleSelect?: () => void;
}

export function StoredSummaryCard({
  summary,
  index,
  onView,
  onPush,
  onPushDM,
  onEmail,
  onPin,
  onArchive,
  onDelete,
  isSelected = false,
  onToggleSelect,
}: StoredSummaryCardProps) {
  const { id: guildId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { formatDateTime } = useTimezone();

  // Format date with timezone and relative time
  const createdDate = parseAsUTC(summary.created_at);
  const formattedDate = formatDateTime(createdDate, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  const relativeTime = formatRelativeTime(summary.created_at);

  const handleScheduleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (summary.schedule_id) {
      navigate(`/guilds/${guildId}/schedules`);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card
        className={`cursor-pointer border-border/50 transition-all hover:border-primary/50 hover:shadow-lg ${
          summary.is_pinned ? "border-primary/30 bg-primary/5" : ""
        } ${isSelected ? "ring-2 ring-primary bg-primary/5" : ""}`}
        onClick={onView}
      >
        <CardContent className="p-5">
          <div className="mb-3 flex items-start justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              {/* ADR-018: Selection checkbox */}
              {onToggleSelect && (
                <Checkbox
                  checked={isSelected}
                  onCheckedChange={() => onToggleSelect()}
                  onClick={(e) => e.stopPropagation()}
                  className="mr-1"
                />
              )}
              {summary.is_pinned && (
                <Pin className="h-4 w-4 text-primary" />
              )}
              <span className="font-medium">{summary.title}</span>
              <span className="text-xs text-muted-foreground font-mono" title={`Summary ID: ${summary.id}`}>
                {summary.id.substring(0, 8)}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="text-sm text-muted-foreground"
                title={formattedDate}
              >
                {relativeTime}
              </span>
              <SummaryActions
                variant="dropdown"
                stopPropagation
                handlers={{
                  onView,
                  onPush,
                  onPushDM,
                  onEmail,
                  onPin,
                  onArchive,
                  onDelete,
                }}
                state={{
                  isPinned: summary.is_pinned,
                  isArchived: summary.is_archived,
                }}
              />
            </div>
          </div>

          <div className="mb-3 flex flex-wrap gap-2">
            {/* ADR-008: Source badge */}
            {(() => {
              const sourceBadge = getSourceBadge(summary.source);
              if (sourceBadge) {
                const Icon = sourceBadge.icon;
                return (
                  <Badge variant="outline" className={sourceBadge.className}>
                    {Icon && <Icon className="mr-1 h-3 w-3" />}
                    {sourceBadge.label}
                  </Badge>
                );
              }
              return null;
            })()}
            {/* Platform badge (Discord/Slack/WhatsApp) */}
            {(() => {
              const platformBadge = getPlatformBadge(summary.archive_source_key);
              if (platformBadge) {
                return (
                  <Badge variant="outline" className={platformBadge.className}>
                    {platformBadge.label}
                  </Badge>
                );
              }
              return null;
            })()}
            {/* ADR-009: Show schedule name for scheduled summaries */}
            {summary.source === "scheduled" && summary.schedule_name && (
              <Badge
                variant="outline"
                className="border-blue-500/50 text-blue-600 cursor-pointer hover:bg-blue-500/10"
                onClick={handleScheduleClick}
              >
                <Clock className="mr-1 h-3 w-3" />
                {summary.schedule_name}
              </Badge>
            )}
            <Badge variant="outline">
              {summary.source_channel_ids.length} channel
              {summary.source_channel_ids.length > 1 ? "s" : ""}
            </Badge>
            {summary.has_references && (
              <Badge variant="secondary">Grounded</Badge>
            )}
            {summary.pushed_to_channels.length > 0 && (
              <Badge variant="outline" className="border-green-500/50 text-green-600">
                <Send className="mr-1 h-3 w-3" />
                Pushed
              </Badge>
            )}
            {/* ADR-041: Partial access indicator */}
            {summary.has_access_issues && (
              <Badge variant="outline" className="bg-amber-500/10 text-amber-600 border-amber-500/30">
                <AlertTriangle className="mr-1 h-3 w-3" />
                Partial Access {summary.access_coverage_percent !== undefined && `(${Math.round(summary.access_coverage_percent)}%)`}
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-4 text-sm text-muted-foreground flex-wrap">
            <div className="flex items-center gap-1.5">
              <MessageSquare className="h-4 w-4" />
              <span>{summary.message_count} messages</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Calendar className="h-4 w-4" />
              <span>{summary.key_points_count} key points</span>
            </div>
            {summary.action_items_count > 0 && (
              <div className="flex items-center gap-1.5">
                <span>{summary.action_items_count} action items</span>
              </div>
            )}
            {/* ADR-008: Show archive period for archive summaries */}
            {summary.source === "archive" && summary.archive_period && (
              <div className="flex items-center gap-1.5 text-orange-600">
                <History className="h-4 w-4" />
                <span>{summary.archive_granularity}: {summary.archive_period}</span>
              </div>
            )}
          </div>

          {/* Generation details - how the summary was made */}
          {(summary.summary_length || summary.perspective || summary.model_used) && (
            <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
              <Settings2 className="h-3 w-3" />
              {summary.summary_length && (
                <span className="capitalize">{summary.summary_length}</span>
              )}
              {summary.perspective && summary.perspective !== "general" && (
                <span className="capitalize">{summary.perspective} view</span>
              )}
              {summary.model_used && (
                <span className="flex items-center gap-1">
                  <Sparkles className="h-3 w-3" />
                  {summary.model_used.replace("claude-", "").replace("-", " ")}
                </span>
              )}
            </div>
          )}

          {summary.tags.length > 0 && (
            <div className="mt-3 flex items-center gap-2">
              <Tag className="h-3 w-3 text-muted-foreground" />
              <div className="flex flex-wrap gap-1">
                {summary.tags.map((tag) => (
                  <Badge key={tag} variant="outline" className="text-xs">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
