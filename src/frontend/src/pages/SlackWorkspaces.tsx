import { useState } from "react";
import { motion } from "framer-motion";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import {
  useSlackWorkspaces,
  useSlackChannels,
  useSlackStatus,
  useConnectSlack,
  useDisconnectSlack,
  useSyncSlackWorkspace,
  useUpdateSlackChannel,
} from "@/hooks/useSlack";
import { useGuilds } from "@/hooks/useGuilds";
import {
  SlackWorkspaceCard,
  SlackWorkspaceCardSkeleton,
} from "@/components/slack/SlackWorkspaceCard";
import { SlackChannelList } from "@/components/slack/SlackChannelList";
import type { SlackWorkspace, SlackScopeTier } from "@/types/slack";
import {
  Plus,
  AlertCircle,
  Slack,
  Globe,
  Lock,
  Info,
} from "lucide-react";

export function SlackWorkspaces() {
  const { toast } = useToast();

  // State
  const [connectDialogOpen, setConnectDialogOpen] = useState(false);
  const [selectedGuildId, setSelectedGuildId] = useState<string>("");
  const [selectedScopeTier, setSelectedScopeTier] = useState<SlackScopeTier>("public");
  const [selectedWorkspace, setSelectedWorkspace] = useState<SlackWorkspace | null>(null);
  const [channelSheetOpen, setChannelSheetOpen] = useState(false);

  // Queries
  const { data: workspaces, isLoading: workspacesLoading, error: workspacesError } = useSlackWorkspaces();
  const { data: slackStatus } = useSlackStatus();
  const { data: guilds } = useGuilds();
  const {
    data: channels,
    isLoading: channelsLoading,
  } = useSlackChannels(selectedWorkspace?.workspace_id || "");

  // Mutations
  const connectSlack = useConnectSlack();
  const disconnectSlack = useDisconnectSlack();
  const syncWorkspace = useSyncSlackWorkspace();
  const updateChannel = useUpdateSlackChannel(selectedWorkspace?.workspace_id || "");

  // Handlers
  const handleConnect = () => {
    if (!selectedGuildId) {
      toast({
        title: "Select a server",
        description: "Please select a Discord server to link the Slack workspace to.",
        variant: "destructive",
      });
      return;
    }

    connectSlack.mutate(
      { guild_id: selectedGuildId, scope_tier: selectedScopeTier },
      {
        onError: (error: Error & { message?: string }) => {
          toast({
            title: "Connection failed",
            description: error.message || "Could not start Slack OAuth flow.",
            variant: "destructive",
          });
        },
      }
    );
  };

  const handleDisconnect = (workspaceId: string) => {
    disconnectSlack.mutate(workspaceId, {
      onSuccess: () => {
        toast({
          title: "Workspace disconnected",
          description: "The Slack workspace has been removed.",
        });
      },
      onError: (error: Error & { message?: string }) => {
        toast({
          title: "Disconnect failed",
          description: error.message || "Could not disconnect workspace.",
          variant: "destructive",
        });
      },
    });
  };

  const handleSync = (workspaceId: string) => {
    syncWorkspace.mutate(workspaceId, {
      onSuccess: (data) => {
        toast({
          title: "Sync complete",
          description: `Synced ${data.channels_synced} channels and ${data.users_synced} users.`,
        });
      },
      onError: (error: Error & { message?: string }) => {
        toast({
          title: "Sync failed",
          description: error.message || "Could not sync workspace.",
          variant: "destructive",
        });
      },
    });
  };

  const handleViewChannels = (workspace: SlackWorkspace) => {
    setSelectedWorkspace(workspace);
    setChannelSheetOpen(true);
  };

  const handleUpdateChannel = (
    channelId: string,
    updates: { auto_summarize?: boolean; is_sensitive?: boolean }
  ) => {
    updateChannel.mutate(
      { channelId, updates },
      {
        onError: (error: Error & { message?: string }) => {
          toast({
            title: "Update failed",
            description: error.message || "Could not update channel settings.",
            variant: "destructive",
          });
        },
      }
    );
  };

  // Check if Slack is configured
  const isSlackConfigured = slackStatus?.configured ?? true;

  return (
    <div className="min-h-screen bg-background">
      <main className="container py-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 flex items-start justify-between"
        >
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#4A154B]">
                <Slack className="h-6 w-6 text-white" />
              </div>
              <h1 className="text-3xl font-bold">Slack Workspaces</h1>
            </div>
            <p className="text-muted-foreground">
              Connect Slack workspaces to generate summaries from your team conversations.
            </p>
          </div>
          <Button
            onClick={() => setConnectDialogOpen(true)}
            disabled={!isSlackConfigured}
          >
            <Plus className="mr-2 h-4 w-4" />
            Connect Workspace
          </Button>
        </motion.div>

        {/* Not Configured Warning */}
        {!isSlackConfigured && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <Card className="border-amber-500/50 bg-amber-500/10">
              <CardContent className="flex items-center gap-4 p-4">
                <AlertCircle className="h-6 w-6 text-amber-500 shrink-0" />
                <div>
                  <p className="font-medium text-amber-600 dark:text-amber-400">
                    Slack Integration Not Configured
                  </p>
                  <p className="text-sm text-muted-foreground">
                    The Slack app credentials are not configured. Contact your administrator
                    to set up the SLACK_CLIENT_ID and SLACK_CLIENT_SECRET environment variables.
                  </p>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Error State */}
        {workspacesError && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <AlertCircle className="mb-4 h-12 w-12 text-destructive" />
            <h2 className="mb-2 text-xl font-semibold">Failed to load workspaces</h2>
            <p className="text-muted-foreground">Please try refreshing the page</p>
          </div>
        )}

        {/* Workspace List */}
        <div className="space-y-4">
          {workspacesLoading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <SlackWorkspaceCardSkeleton key={i} />
            ))
          ) : workspaces && workspaces.length > 0 ? (
            workspaces.map((workspace, index) => (
              <SlackWorkspaceCard
                key={workspace.workspace_id}
                workspace={workspace}
                index={index}
                onViewChannels={handleViewChannels}
                onSync={handleSync}
                onDisconnect={handleDisconnect}
                isSyncing={syncWorkspace.isPending}
                isDisconnecting={disconnectSlack.isPending}
              />
            ))
          ) : (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center justify-center py-16">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                  <Slack className="h-8 w-8 text-muted-foreground" />
                </div>
                <h3 className="text-lg font-semibold mb-2">No Slack Workspaces Connected</h3>
                <p className="text-muted-foreground text-center max-w-md mb-4">
                  Connect a Slack workspace to start generating summaries from your team conversations.
                </p>
                <Button onClick={() => setConnectDialogOpen(true)} disabled={!isSlackConfigured}>
                  <Plus className="mr-2 h-4 w-4" />
                  Connect Your First Workspace
                </Button>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Connect Dialog */}
        <Dialog open={connectDialogOpen} onOpenChange={setConnectDialogOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Slack className="h-5 w-5" />
                Connect Slack Workspace
              </DialogTitle>
              <DialogDescription>
                Install SummaryBot to your Slack workspace to enable AI-powered summaries.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              {/* Guild Selection */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Link to Discord Server</label>
                <Select value={selectedGuildId} onValueChange={setSelectedGuildId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a Discord server" />
                  </SelectTrigger>
                  <SelectContent>
                    {guilds?.map((guild) => (
                      <SelectItem key={guild.id} value={guild.id}>
                        {guild.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Slack summaries will be accessible from this Discord server&apos;s dashboard.
                </p>
              </div>

              {/* Scope Tier Selection */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Access Level</label>
                <div className="grid gap-3">
                  <Card
                    className={`cursor-pointer transition-colors ${
                      selectedScopeTier === "public"
                        ? "border-primary bg-primary/5"
                        : "hover:border-border"
                    }`}
                    onClick={() => setSelectedScopeTier("public")}
                  >
                    <CardContent className="flex items-start gap-3 p-4">
                      <Globe className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">Public Channels</span>
                          <Badge variant="secondary" className="text-xs">
                            Recommended
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          Access only public channels. Best for getting started.
                        </p>
                      </div>
                    </CardContent>
                  </Card>

                  <Card
                    className={`cursor-pointer transition-colors ${
                      selectedScopeTier === "full"
                        ? "border-primary bg-primary/5"
                        : "hover:border-border"
                    }`}
                    onClick={() => setSelectedScopeTier("full")}
                  >
                    <CardContent className="flex items-start gap-3 p-4">
                      <Lock className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <span className="font-medium">Full Access</span>
                        <p className="text-sm text-muted-foreground mt-1">
                          Access public and private channels the bot is invited to.
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>

              {/* Scopes Info */}
              {slackStatus?.scopes && (
                <div className="rounded-lg border bg-muted/50 p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <Info className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Requested Permissions</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(selectedScopeTier === "public"
                      ? slackStatus.scopes.public
                      : slackStatus.scopes.full
                    ).map((scope) => (
                      <Badge key={scope} variant="outline" className="text-xs font-mono">
                        {scope}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setConnectDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleConnect}
                disabled={connectSlack.isPending || !selectedGuildId}
              >
                {connectSlack.isPending ? "Connecting..." : "Continue to Slack"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Channel List Sheet */}
        {selectedWorkspace && (
          <SlackChannelList
            workspace={selectedWorkspace}
            channels={channels || []}
            isLoading={channelsLoading}
            onUpdateChannel={handleUpdateChannel}
            isUpdating={updateChannel.isPending}
            open={channelSheetOpen}
            onOpenChange={setChannelSheetOpen}
          />
        )}
      </main>
    </div>
  );
}
