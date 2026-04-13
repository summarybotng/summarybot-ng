import { useState } from "react";
import { motion } from "framer-motion";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Hash,
  Lock,
  Archive,
  Users,
  Search,
  AlertTriangle,
  MessageSquare,
  X,
} from "lucide-react";
import type { SlackChannel } from "@/types/slack";
import type { SlackWorkspace } from "@/types/slack";

interface SlackChannelListProps {
  workspace: SlackWorkspace;
  channels: SlackChannel[];
  isLoading: boolean;
  onUpdateChannel: (
    channelId: string,
    updates: { auto_summarize?: boolean; is_sensitive?: boolean }
  ) => void;
  isUpdating: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SlackChannelList({
  workspace,
  channels,
  isLoading,
  onUpdateChannel,
  isUpdating,
  open,
  onOpenChange,
}: SlackChannelListProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);

  // Filter channels
  const filteredChannels = channels.filter((channel) => {
    const matchesSearch = channel.channel_name
      .toLowerCase()
      .includes(searchQuery.toLowerCase());
    const matchesArchived = showArchived || !channel.is_archived;
    return matchesSearch && matchesArchived;
  });

  // Group channels by type
  const publicChannels = filteredChannels.filter(
    (ch) => ch.channel_type === "public"
  );
  const privateChannels = filteredChannels.filter(
    (ch) => ch.channel_type === "private"
  );

  const channelTypeConfig = {
    public: { icon: Hash, label: "Public" },
    private: { icon: Lock, label: "Private" },
    dm: { icon: MessageSquare, label: "DM" },
    mpim: { icon: Users, label: "Group DM" },
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-2xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Hash className="h-5 w-5" />
            Channels - {workspace.workspace_name}
          </SheetTitle>
          <SheetDescription>
            Manage auto-summarization and sensitivity settings for Slack
            channels. Only channels the bot has access to are shown.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-6">
          {/* Search & Filters */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search channels..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
              {searchQuery && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2"
                  onClick={() => setSearchQuery("")}
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="show-archived"
                checked={showArchived}
                onCheckedChange={setShowArchived}
              />
              <label
                htmlFor="show-archived"
                className="text-sm text-muted-foreground cursor-pointer"
              >
                Show archived
              </label>
            </div>
          </div>

          {/* Stats */}
          <div className="flex gap-4 text-sm text-muted-foreground">
            <span>{publicChannels.length} public</span>
            <span>{privateChannels.length} private</span>
            <span>
              {channels.filter((ch) => ch.auto_summarize).length} auto-summarize
            </span>
          </div>

          {/* Channel Table */}
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : filteredChannels.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              {searchQuery
                ? `No channels matching "${searchQuery}"`
                : "No channels found"}
            </div>
          ) : (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3 }}
            >
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Channel</TableHead>
                    <TableHead className="w-24 text-center">Members</TableHead>
                    <TableHead className="w-28 text-center">
                      <Tooltip>
                        <TooltipTrigger className="cursor-help">
                          Auto-Summarize
                        </TooltipTrigger>
                        <TooltipContent>
                          Automatically generate summaries for this channel
                        </TooltipContent>
                      </Tooltip>
                    </TableHead>
                    <TableHead className="w-24 text-center">
                      <Tooltip>
                        <TooltipTrigger className="cursor-help">
                          Sensitive
                        </TooltipTrigger>
                        <TooltipContent>
                          Mark as sensitive to exclude from cross-channel summaries
                        </TooltipContent>
                      </Tooltip>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredChannels.map((channel) => {
                    const typeConfig =
                      channelTypeConfig[channel.channel_type] ||
                      channelTypeConfig.public;
                    const TypeIcon = typeConfig.icon;

                    return (
                      <TableRow
                        key={channel.channel_id}
                        className={channel.is_archived ? "opacity-60" : ""}
                      >
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <TypeIcon className="h-4 w-4 text-muted-foreground shrink-0" />
                            <span className="font-medium">
                              {channel.channel_name}
                            </span>
                            {channel.is_archived && (
                              <Badge
                                variant="outline"
                                className="text-xs shrink-0"
                              >
                                <Archive className="mr-1 h-3 w-3" />
                                Archived
                              </Badge>
                            )}
                            {channel.is_shared && (
                              <Badge
                                variant="secondary"
                                className="text-xs shrink-0"
                              >
                                Shared
                              </Badge>
                            )}
                          </div>
                          {channel.topic && (
                            <p className="mt-1 text-xs text-muted-foreground truncate max-w-md">
                              {channel.topic}
                            </p>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          <div className="flex items-center justify-center gap-1">
                            <Users className="h-3 w-3 text-muted-foreground" />
                            <span className="text-sm">
                              {channel.member_count}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-center">
                          <Switch
                            checked={channel.auto_summarize}
                            onCheckedChange={(checked) =>
                              onUpdateChannel(channel.channel_id, {
                                auto_summarize: checked,
                              })
                            }
                            disabled={isUpdating || channel.is_archived}
                          />
                        </TableCell>
                        <TableCell className="text-center">
                          <div className="flex items-center justify-center gap-1">
                            <Switch
                              checked={channel.is_sensitive}
                              onCheckedChange={(checked) =>
                                onUpdateChannel(channel.channel_id, {
                                  is_sensitive: checked,
                                })
                              }
                              disabled={isUpdating}
                            />
                            {channel.is_sensitive && (
                              <AlertTriangle className="h-3 w-3 text-amber-500" />
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </motion.div>
          )}

          {/* Scope Warning */}
          {workspace.scope_tier === "public" && privateChannels.length === 0 && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4">
              <div className="flex gap-3">
                <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0" />
                <div>
                  <p className="font-medium text-amber-600 dark:text-amber-400">
                    Public Channels Only
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    This workspace is connected with the &quot;Public Channels&quot;
                    scope. To access private channels, reconnect the workspace
                    with &quot;Full Access&quot; permissions.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
