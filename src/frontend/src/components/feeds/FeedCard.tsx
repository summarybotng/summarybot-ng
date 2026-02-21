import { motion } from "framer-motion";
import { formatDistanceToNow } from "date-fns";
import { parseAsUTC } from "@/contexts/TimezoneContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Copy,
  Pencil,
  Trash2,
  RefreshCw,
  Rss,
  Hash,
  Globe,
  Lock,
  ExternalLink,
} from "lucide-react";
import type { Feed } from "@/types";
import { useToast } from "@/hooks/use-toast";

interface FeedCardProps {
  feed: Feed;
  index: number;
  onEdit: (feed: Feed) => void;
  onDelete: (feedId: string) => void;
  onRegenerateToken: (feedId: string) => void;
  isDeleting: boolean;
  isRegenerating: boolean;
}

export function FeedCard({
  feed,
  index,
  onEdit,
  onDelete,
  onRegenerateToken,
  isDeleting,
  isRegenerating,
}: FeedCardProps) {
  const { toast } = useToast();

  const copyUrl = async () => {
    await navigator.clipboard.writeText(feed.url);
    toast({
      title: "URL copied",
      description: "Feed URL copied to clipboard",
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card className="border-border/50 transition-colors hover:border-border">
        <CardContent className="p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex-1 space-y-2">
              {/* Title & Badges */}
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-semibold">{feed.title || "Untitled Feed"}</h3>
                <Badge variant="outline" className="text-xs">
                  {feed.feed_type.toUpperCase()}
                </Badge>
                {feed.is_public ? (
                  <Badge variant="secondary" className="text-xs">
                    <Globe className="mr-1 h-3 w-3" />
                    Public
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-xs">
                    <Lock className="mr-1 h-3 w-3" />
                    Private
                  </Badge>
                )}
              </div>

              {/* Channel */}
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                {feed.channel_name ? (
                  <>
                    <Hash className="h-4 w-4" />
                    <span>{feed.channel_name}</span>
                  </>
                ) : (
                  <>
                    <Rss className="h-4 w-4" />
                    <span>All Channels</span>
                  </>
                )}
              </div>

              {/* Stats */}
              <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                <span>
                  {feed.access_count} access{feed.access_count !== 1 ? "es" : ""}
                </span>
                {feed.last_accessed && (
                  <span>
                    Last accessed{" "}
                    {formatDistanceToNow(parseAsUTC(feed.last_accessed), {
                      addSuffix: true,
                    })}
                  </span>
                )}
                <span>
                  Created{" "}
                  {formatDistanceToNow(parseAsUTC(feed.created_at), {
                    addSuffix: true,
                  })}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" onClick={copyUrl}>
                    <Copy className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Copy URL</TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => window.open(feed.url, "_blank")}
                  >
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Open Feed</TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" onClick={() => onEdit(feed)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Edit</TooltipContent>
              </Tooltip>

              {/* Regenerate Token - only for private feeds */}
              {!feed.is_public && (
                <AlertDialog>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          disabled={isRegenerating}
                        >
                          <RefreshCw
                            className={`h-4 w-4 ${isRegenerating ? "animate-spin" : ""}`}
                          />
                        </Button>
                      </AlertDialogTrigger>
                    </TooltipTrigger>
                    <TooltipContent>Regenerate Token</TooltipContent>
                  </Tooltip>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Regenerate Token?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will invalidate the current feed URL. Any feed readers
                        using the old URL will stop working.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => onRegenerateToken(feed.id)}
                      >
                        Regenerate
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}

              {/* Delete */}
              <AlertDialog>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        disabled={isDeleting}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </AlertDialogTrigger>
                  </TooltipTrigger>
                  <TooltipContent>Delete</TooltipContent>
                </Tooltip>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete Feed?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will permanently delete the feed. Feed readers using this
                      URL will no longer receive updates.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => onDelete(feed.id)}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
