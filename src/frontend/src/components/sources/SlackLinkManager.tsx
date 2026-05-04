/**
 * Slack Link Manager Component (ADR-085)
 *
 * Allows linking/unlinking Slack workspaces to Discord guilds for multi-guild access.
 */

import { useState } from "react";
import { Slack, Plus, X, Link2, Unlink, Loader2, Check } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  useSlackWorkspaces,
  useSlackGuildLinks,
  useAddSlackGuildLink,
  useRemoveSlackGuildLink,
  type LinkedSlackWorkspace,
} from "@/hooks/useSlack";

interface SlackLinkManagerProps {
  guildId: string;
  guildName?: string;
}

export function SlackLinkManager({ guildId, guildName }: SlackLinkManagerProps) {
  const [open, setOpen] = useState(false);

  // Fetch all workspaces the user has access to
  const { data: allWorkspaces, isLoading: workspacesLoading } = useSlackWorkspaces();

  // Fetch workspaces linked to this guild
  const { data: linkedData, isLoading: linksLoading } = useSlackGuildLinks(guildId);
  const linkedWorkspaces = linkedData?.workspaces || [];

  // Mutations
  const addLink = useAddSlackGuildLink();
  const removeLink = useRemoveSlackGuildLink();

  // Find workspaces that are NOT linked to this guild (available to add)
  const linkedIds = new Set(linkedWorkspaces.map((w) => w.workspace_id));
  const availableWorkspaces = (allWorkspaces || []).filter(
    (ws) => !linkedIds.has(ws.workspace_id)
  );

  const isLoading = workspacesLoading || linksLoading;

  const handleLink = async (workspaceId: string, canSummarize: boolean) => {
    await addLink.mutateAsync({
      guildId,
      workspaceId,
      canView: true,
      canSummarize,
    });
  };

  const handleUnlink = async (workspaceId: string) => {
    await removeLink.mutateAsync({ guildId, workspaceId });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Slack className="mr-2 h-4 w-4 text-purple-500" />
          Manage Slack
          {linkedWorkspaces.length > 0 && (
            <Badge variant="secondary" className="ml-2">
              {linkedWorkspaces.length}
            </Badge>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Slack className="h-5 w-5 text-purple-500" />
            Slack Workspaces
          </DialogTitle>
          <DialogDescription>
            Link Slack workspaces to {guildName || "this guild"} to view their channels on the Sources page.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* Linked workspaces */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium">Linked Workspaces</h4>
              {linkedWorkspaces.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No Slack workspaces linked to this guild yet.
                </p>
              ) : (
                <div className="space-y-2">
                  {linkedWorkspaces.map((ws) => (
                    <LinkedWorkspaceItem
                      key={ws.workspace_id}
                      workspace={ws}
                      onUnlink={() => handleUnlink(ws.workspace_id)}
                      isUnlinking={removeLink.isPending}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Available workspaces to link */}
            {availableWorkspaces.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-sm font-medium">Available to Link</h4>
                <div className="space-y-2">
                  {availableWorkspaces.map((ws) => (
                    <AvailableWorkspaceItem
                      key={ws.workspace_id}
                      workspace={ws}
                      onLink={(canSummarize) => handleLink(ws.workspace_id, canSummarize)}
                      isLinking={addLink.isPending}
                    />
                  ))}
                </div>
              </div>
            )}

            {linkedWorkspaces.length === 0 && availableWorkspaces.length === 0 && (
              <div className="text-center py-4">
                <Slack className="mx-auto h-10 w-10 text-muted-foreground/50" />
                <p className="mt-2 text-sm text-muted-foreground">
                  No Slack workspaces available. Connect a workspace from the Slack integration page first.
                </p>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

interface LinkedWorkspaceItemProps {
  workspace: LinkedSlackWorkspace;
  onUnlink: () => void;
  isUnlinking: boolean;
}

function LinkedWorkspaceItem({ workspace, onUnlink, isUnlinking }: LinkedWorkspaceItemProps) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-purple-500/20 bg-purple-500/5 px-4 py-3">
      <div className="flex items-center gap-3">
        <Slack className="h-4 w-4 text-purple-500" />
        <div>
          <span className="font-medium">{workspace.workspace_name}</span>
          {workspace.workspace_domain && (
            <span className="ml-2 text-xs text-muted-foreground">
              {workspace.workspace_domain}.slack.com
            </span>
          )}
        </div>
        {workspace.is_primary && (
          <Badge variant="outline" className="text-xs">
            Primary
          </Badge>
        )}
      </div>
      {!workspace.is_primary && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onUnlink}
          disabled={isUnlinking}
          className="text-muted-foreground hover:text-destructive"
        >
          {isUnlinking ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Unlink className="h-4 w-4" />
          )}
        </Button>
      )}
    </div>
  );
}

interface AvailableWorkspaceItemProps {
  workspace: { workspace_id: string; workspace_name: string; workspace_domain?: string };
  onLink: (canSummarize: boolean) => void;
  isLinking: boolean;
}

function AvailableWorkspaceItem({ workspace, onLink, isLinking }: AvailableWorkspaceItemProps) {
  const [canSummarize, setCanSummarize] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const handleLink = () => {
    onLink(canSummarize);
    setExpanded(false);
  };

  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Slack className="h-4 w-4 text-muted-foreground" />
          <div>
            <span className="font-medium">{workspace.workspace_name}</span>
            {workspace.workspace_domain && (
              <span className="ml-2 text-xs text-muted-foreground">
                {workspace.workspace_domain}.slack.com
              </span>
            )}
          </div>
        </div>
        {!expanded ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setExpanded(true)}
          >
            <Plus className="mr-1 h-3 w-3" />
            Link
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {expanded && (
        <div className="mt-4 space-y-4 border-t pt-4">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <Label htmlFor={`summarize-${workspace.workspace_id}`}>
                Enable summarization
              </Label>
              <p className="text-xs text-muted-foreground">
                Allow generating summaries from this workspace
              </p>
            </div>
            <Switch
              id={`summarize-${workspace.workspace_id}`}
              checked={canSummarize}
              onCheckedChange={setCanSummarize}
            />
          </div>
          <Button
            onClick={handleLink}
            disabled={isLinking}
            className="w-full"
          >
            {isLinking ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Link2 className="mr-2 h-4 w-4" />
            )}
            Link to this Guild
          </Button>
        </div>
      )}
    </div>
  );
}
