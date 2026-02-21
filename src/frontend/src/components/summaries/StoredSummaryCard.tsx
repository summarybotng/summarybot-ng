/**
 * Stored Summary Card Component (ADR-005, ADR-008)
 *
 * ADR-008: Extended to show source badges for unified summary experience.
 */

import { motion } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Pin,
  Archive,
  Trash2,
  MoreVertical,
  MessageSquare,
  Calendar,
  Send,
  Eye,
  Tag,
  History,
  Clock,
} from "lucide-react";
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

interface StoredSummaryCardProps {
  summary: StoredSummary;
  index: number;
  onView: () => void;
  onPush: () => void;
  onPin: () => void;
  onArchive: () => void;
  onDelete: () => void;
}

export function StoredSummaryCard({
  summary,
  index,
  onView,
  onPush,
  onPin,
  onArchive,
  onDelete,
}: StoredSummaryCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card
        className={`cursor-pointer border-border/50 transition-all hover:border-primary/50 hover:shadow-lg ${
          summary.is_pinned ? "border-primary/30 bg-primary/5" : ""
        }`}
        onClick={onView}
      >
        <CardContent className="p-5">
          <div className="mb-3 flex items-start justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              {summary.is_pinned && (
                <Pin className="h-4 w-4 text-primary" />
              )}
              <span className="font-medium">{summary.title}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">
                {new Date(summary.created_at).toLocaleDateString()}
              </span>
              <DropdownMenu>
                <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onView(); }}>
                    <Eye className="mr-2 h-4 w-4" />
                    View Details
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onPush(); }}>
                    <Send className="mr-2 h-4 w-4" />
                    Push to Channel
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onPin(); }}>
                    <Pin className="mr-2 h-4 w-4" />
                    {summary.is_pinned ? "Unpin" : "Pin"}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onArchive(); }}>
                    <Archive className="mr-2 h-4 w-4" />
                    {summary.is_archived ? "Unarchive" : "Archive"}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={(e) => { e.stopPropagation(); onDelete(); }}
                    className="text-destructive"
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
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
