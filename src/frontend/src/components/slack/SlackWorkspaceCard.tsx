import { motion } from "framer-motion";
import { formatRelativeTime } from "@/contexts/TimezoneContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
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
  Hash,
  RefreshCw,
  Unlink,
  ChevronRight,
  Building2,
  Globe,
  Lock,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import type { SlackWorkspace } from "@/types/slack";

interface SlackWorkspaceCardProps {
  workspace: SlackWorkspace;
  index: number;
  onViewChannels: (workspace: SlackWorkspace) => void;
  onSync: (workspaceId: string) => void;
  onDisconnect: (workspaceId: string) => void;
  isSyncing: boolean;
  isDisconnecting: boolean;
  channelCount?: number;
}

export function SlackWorkspaceCard({
  workspace,
  index,
  onViewChannels,
  onSync,
  onDisconnect,
  isSyncing,
  isDisconnecting,
  channelCount,
}: SlackWorkspaceCardProps) {
  const scopeTierConfig = {
    public: {
      label: "Public Channels",
      icon: Globe,
      variant: "secondary" as const,
    },
    full: {
      label: "Full Access",
      icon: Lock,
      variant: "default" as const,
    },
  };

  const scopeConfig = scopeTierConfig[workspace.scope_tier] || scopeTierConfig.public;
  const ScopeIcon = scopeConfig.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.05 }}
    >
      <Card className="group border-border/50 bg-card/50 transition-all hover:border-border hover:bg-card">
        <CardContent className="p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            {/* Workspace Info */}
            <div className="flex items-start gap-4">
              <Avatar className="h-12 w-12 rounded-xl">
                <AvatarFallback className="rounded-xl bg-[#4A154B]/20 text-[#4A154B] text-lg font-semibold">
                  {workspace.workspace_name.slice(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>

              <div className="flex-1 space-y-2">
                {/* Name & Badges */}
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold text-lg">
                    {workspace.workspace_name}
                  </h3>
                  {workspace.is_enterprise && (
                    <Badge variant="outline" className="text-xs">
                      <Building2 className="mr-1 h-3 w-3" />
                      Enterprise
                    </Badge>
                  )}
                  <Badge variant={scopeConfig.variant} className="text-xs">
                    <ScopeIcon className="mr-1 h-3 w-3" />
                    {scopeConfig.label}
                  </Badge>
                  {workspace.enabled ? (
                    <Badge variant="default" className="text-xs bg-green-600">
                      <CheckCircle2 className="mr-1 h-3 w-3" />
                      Active
                    </Badge>
                  ) : (
                    <Badge variant="destructive" className="text-xs">
                      <XCircle className="mr-1 h-3 w-3" />
                      Disabled
                    </Badge>
                  )}
                </div>

                {/* Domain */}
                {workspace.workspace_domain && (
                  <p className="text-sm text-muted-foreground">
                    {workspace.workspace_domain}.slack.com
                  </p>
                )}

                {/* Stats */}
                <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                  {channelCount !== undefined && (
                    <div className="flex items-center gap-1.5">
                      <Hash className="h-4 w-4" />
                      <span>
                        {channelCount} channel{channelCount !== 1 ? "s" : ""}
                      </span>
                    </div>
                  )}
                  {workspace.last_sync_at && (
                    <span>
                      Last synced {formatRelativeTime(workspace.last_sync_at)}
                    </span>
                  )}
                  {workspace.installed_at && (
                    <span>
                      Connected {formatRelativeTime(workspace.installed_at)}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 shrink-0">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => onSync(workspace.workspace_id)}
                    disabled={isSyncing}
                  >
                    <RefreshCw
                      className={`h-4 w-4 ${isSyncing ? "animate-spin" : ""}`}
                    />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Sync Channels</TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onViewChannels(workspace)}
                  >
                    View Channels
                    <ChevronRight className="ml-1 h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>View and manage channels</TooltipContent>
              </Tooltip>

              <AlertDialog>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        disabled={isDisconnecting}
                      >
                        <Unlink className="h-4 w-4" />
                      </Button>
                    </AlertDialogTrigger>
                  </TooltipTrigger>
                  <TooltipContent>Disconnect Workspace</TooltipContent>
                </Tooltip>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Disconnect Slack Workspace?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will remove the connection to{" "}
                      <strong>{workspace.workspace_name}</strong>. You will need
                      to reinstall the app to reconnect. Existing summaries will
                      be preserved.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => onDisconnect(workspace.workspace_id)}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      Disconnect
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

/**
 * Skeleton loader for workspace card
 */
export function SlackWorkspaceCardSkeleton() {
  return (
    <Card className="border-border/50">
      <CardContent className="p-5">
        <div className="flex items-start gap-4">
          <div className="h-12 w-12 rounded-xl bg-muted animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-6 w-48 bg-muted animate-pulse rounded" />
            <div className="h-4 w-32 bg-muted animate-pulse rounded" />
            <div className="flex gap-4">
              <div className="h-4 w-24 bg-muted animate-pulse rounded" />
              <div className="h-4 w-32 bg-muted animate-pulse rounded" />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
