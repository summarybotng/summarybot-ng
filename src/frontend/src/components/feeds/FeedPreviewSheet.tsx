/**
 * Feed Preview Sheet Component (ADR-037 Phase 4)
 *
 * Displays formatted feed content in a side sheet for preview.
 */

import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  ExternalLink,
  Copy,
  Check,
  MessageSquare,
  ListChecks,
  CheckCircle2,
  Filter,
  Loader2,
  ChevronRight,
  Rss,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import { useFeedPreview, type FeedPreviewItem } from "@/hooks/useFeedPreview";
import { FilterCriteriaSummary } from "@/components/filters";
import { useTimezone } from "@/contexts/TimezoneContext";
import type { Feed } from "@/types";

interface FeedPreviewSheetProps {
  feed: Feed | null;
  guildId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function FeedPreviewSheet({
  feed,
  guildId,
  open,
  onOpenChange,
}: FeedPreviewSheetProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { formatRelativeTime } = useTimezone();
  const [page, setPage] = useState(1);
  const [copied, setCopied] = useState(false);
  const prevFeedIdRef = useRef<string | null>(null);

  // Reset page when feed changes
  useEffect(() => {
    if (feed?.id && feed.id !== prevFeedIdRef.current) {
      setPage(1);
      prevFeedIdRef.current = feed.id;
    }
  }, [feed?.id]);

  const { data, isLoading, isError } = useFeedPreview(
    guildId,
    feed?.id ?? null,
    { page, limit: 10 }
  );

  const handleCopyUrl = async () => {
    if (!feed?.url) return;
    try {
      await navigator.clipboard.writeText(feed.url);
      setCopied(true);
      toast({
        title: "Copied",
        description: "Feed URL copied to clipboard",
      });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({
        title: "Error",
        description: "Failed to copy URL",
        variant: "destructive",
      });
    }
  };

  const handleOpenRawFeed = () => {
    if (feed?.url) {
      window.open(feed.url, "_blank");
    }
  };

  const handleViewSummary = (summaryId: string) => {
    navigate(`/guilds/${guildId}/summaries?selected=${summaryId}`);
    onOpenChange(false);
  };

  const handleLoadMore = () => {
    setPage((p) => p + 1);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl md:max-w-2xl">
        <SheetHeader>
          <div className="flex items-center gap-2">
            <Rss className="h-5 w-5 text-muted-foreground" />
            <SheetTitle className="text-lg">{data?.title || feed?.title || "Feed Preview"}</SheetTitle>
          </div>
          <SheetDescription className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline">{data?.feed_type?.toUpperCase() || "RSS"}</Badge>
            <span>•</span>
            <span>{data?.item_count ?? 0} items</span>
            {data?.last_updated && (
              <>
                <span>•</span>
                <span>Updated {formatRelativeTime(data.last_updated)}</span>
              </>
            )}
          </SheetDescription>
        </SheetHeader>

        {/* Actions */}
        <div className="flex gap-2 mt-4 mb-4">
          <Button variant="outline" size="sm" onClick={handleCopyUrl}>
            {copied ? (
              <Check className="h-4 w-4 mr-2" />
            ) : (
              <Copy className="h-4 w-4 mr-2" />
            )}
            Copy URL
          </Button>
          <Button variant="outline" size="sm" onClick={handleOpenRawFeed}>
            <ExternalLink className="h-4 w-4 mr-2" />
            Open Raw Feed
          </Button>
        </div>

        {/* Active Filters */}
        {data?.criteria && Object.keys(data.criteria).length > 0 && (
          <div className="mb-4 p-3 bg-muted/50 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Active Filters</span>
            </div>
            <FilterCriteriaSummary
              criteria={data.criteria}
              onUpdate={() => {}}
              compact
            />
          </div>
        )}

        {/* Content */}
        <ScrollArea className="h-[calc(100vh-280px)]">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Card key={i}>
                  <CardContent className="p-4">
                    <Skeleton className="h-5 w-3/4 mb-2" />
                    <Skeleton className="h-4 w-1/2 mb-3" />
                    <Skeleton className="h-16 w-full" />
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : isError ? (
            <div className="text-center py-8 text-muted-foreground">
              Failed to load feed preview
            </div>
          ) : data?.items.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Rss className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p>No summaries match the feed criteria</p>
            </div>
          ) : (
            <div className="space-y-3 pr-4">
              {data?.items.map((item) => (
                <FeedPreviewCard
                  key={item.id}
                  item={item}
                  formatRelativeTime={formatRelativeTime}
                  onClick={() => handleViewSummary(item.id)}
                />
              ))}

              {data?.has_more && (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={handleLoadMore}
                >
                  Load More
                </Button>
              )}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

interface FeedPreviewCardProps {
  item: FeedPreviewItem;
  formatRelativeTime: (date: string) => string;
  onClick: () => void;
}

function FeedPreviewCard({ item, formatRelativeTime, onClick }: FeedPreviewCardProps) {
  return (
    <Card
      className="cursor-pointer hover:bg-muted/50 transition-colors"
      onClick={onClick}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <h4 className="font-medium text-sm truncate">{item.title}</h4>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1 flex-wrap">
              {item.channel_name && (
                <span className="text-primary">#{item.channel_name}</span>
              )}
              {item.created_at && (
                <span>{formatRelativeTime(item.created_at)}</span>
              )}
              <span className="flex items-center gap-1">
                <MessageSquare className="h-3 w-3" />
                {item.message_count}
              </span>
            </div>
          </div>
          <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        </div>

        <p className="text-sm text-muted-foreground mt-2 line-clamp-3">
          {item.preview}
        </p>

        <div className="flex items-center gap-2 mt-2 flex-wrap">
          {item.has_key_points && (
            <Badge variant="secondary" className="text-xs">
              <ListChecks className="h-3 w-3 mr-1" />
              Key Points
            </Badge>
          )}
          {item.has_action_items && (
            <Badge variant="secondary" className="text-xs">
              <CheckCircle2 className="h-3 w-3 mr-1" />
              Actions
            </Badge>
          )}
          {item.source && (
            <Badge variant="outline" className="text-xs capitalize">
              {item.source}
            </Badge>
          )}
          {item.perspective && item.perspective !== "general" && (
            <Badge variant="outline" className="text-xs capitalize">
              {item.perspective}
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
