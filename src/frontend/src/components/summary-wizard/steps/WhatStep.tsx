/**
 * Step 1: What to Summarize (ADR-089)
 *
 * Platform selection + channel/scope selection
 */

import { useEffect, useState } from "react";
import { useGuild } from "@/hooks/useGuilds";
import { useWhatsAppChats } from "@/hooks/useWhatsApp";
import { useSlackGuildLinks, useSlackChannels } from "@/hooks/useSlack";
import { useCheckChannelPrivacy, type PrivacyWarning } from "@/hooks/useChannelPrivacy";
import { PlatformCard } from "../shared/PlatformCard";
import { ScopeSelector, type ScopeSelectorValue } from "@/components/ScopeSelector";
import { WhatsAppChatSelector } from "@/components/schedules/WhatsAppChatSelector";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { AlertCircle, AlertTriangle } from "lucide-react";
import type { StepProps, Platform, SplitMode } from "../types";

export function WhatStep({ state, onChange, guildId }: StepProps) {
  const { data: guild, isLoading: guildLoading } = useGuild(guildId);
  const { data: whatsappChats } = useWhatsAppChats(guildId);
  const { data: slackLinksData } = useSlackGuildLinks(guildId);
  const [selectedSlackWorkspace, setSelectedSlackWorkspace] = useState<string>("");
  const { data: slackChannels } = useSlackChannels(selectedSlackWorkspace);
  const checkPrivacy = useCheckChannelPrivacy(guildId);
  const [privacyWarnings, setPrivacyWarnings] = useState<PrivacyWarning[]>([]);

  const hasWhatsApp = whatsappChats && whatsappChats.length > 0;
  const linkedSlackWorkspaces = slackLinksData?.workspaces || [];
  const hasSlack = linkedSlackWorkspaces.length > 0;

  // Auto-select first Slack workspace if only one
  useEffect(() => {
    if (state.platform === "slack" && linkedSlackWorkspaces.length === 1 && !selectedSlackWorkspace) {
      setSelectedSlackWorkspace(linkedSlackWorkspaces[0].workspace_id);
    }
  }, [state.platform, linkedSlackWorkspaces, selectedSlackWorkspace]);

  // ADR-046: Check privacy when Discord channels are selected
  useEffect(() => {
    if (state.platform !== "discord" || state.scope !== "channel" || state.channelIds.length === 0) {
      setPrivacyWarnings([]);
      return;
    }

    const timeoutId = setTimeout(() => {
      checkPrivacy.mutateAsync(state.channelIds).then((result) => {
        setPrivacyWarnings(result.warnings);
      }).catch(() => {
        setPrivacyWarnings([]);
      });
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [state.platform, state.scope, state.channelIds.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const handlePlatformChange = (platform: Platform) => {
    // Reset scope when switching platforms
    const newScope = platform === "whatsapp" ? "channel" : state.scope;
    onChange({
      platform,
      scope: newScope,
      channelIds: [],
      categoryId: "",
    });
  };

  const handleScopeChange = (value: ScopeSelectorValue) => {
    onChange({
      scope: value.scope,
      channelIds: value.channelIds,
      categoryId: value.categoryId,
    });
  };

  const scopeValue: ScopeSelectorValue = {
    scope: state.scope,
    channelIds: state.channelIds,
    categoryId: state.categoryId,
  };

  if (guildLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium mb-4">What would you like to summarize?</h3>

        {/* Platform Selection */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          <PlatformCard
            platform="discord"
            selected={state.platform === "discord"}
            onClick={() => handlePlatformChange("discord")}
          />
          <PlatformCard
            platform="slack"
            selected={state.platform === "slack"}
            onClick={() => handlePlatformChange("slack")}
          />
          <PlatformCard
            platform="whatsapp"
            selected={state.platform === "whatsapp"}
            onClick={() => handlePlatformChange("whatsapp")}
            disabled={!hasWhatsApp}
          />
        </div>

        {!hasWhatsApp && (
          <p className="text-xs text-muted-foreground text-center -mt-4 mb-4">
            Import WhatsApp chats to enable WhatsApp summaries
          </p>
        )}
      </div>

      {/* Channel/Scope Selection */}
      <div>
        <h4 className="text-sm font-medium mb-3">Select channels</h4>

        {state.platform === "whatsapp" ? (
          <WhatsAppChatSelector
            guildId={guildId}
            selectedChatIds={state.channelIds}
            onChange={(chatIds) => onChange({ channelIds: chatIds })}
          />
        ) : state.platform === "slack" ? (
          <div className="space-y-4">
            {/* Slack Workspace Selector */}
            {linkedSlackWorkspaces.length > 1 && (
              <div>
                <Label className="text-sm">Workspace</Label>
                <Select
                  value={selectedSlackWorkspace}
                  onValueChange={(v) => {
                    setSelectedSlackWorkspace(v);
                    onChange({ channelIds: [] }); // Reset channels on workspace change
                  }}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Select workspace" />
                  </SelectTrigger>
                  <SelectContent>
                    {linkedSlackWorkspaces.map((ws) => (
                      <SelectItem key={ws.workspace_id} value={ws.workspace_id}>
                        {ws.workspace_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {/* Slack Channel Selector */}
            {selectedSlackWorkspace && slackChannels ? (
              <ScopeSelector
                value={scopeValue}
                onChange={handleScopeChange}
                channels={slackChannels.map((ch) => ({
                  id: ch.id,
                  name: ch.name,
                  type: ch.is_private ? 2 : 0,
                }))}
                categories={[]}
                allowedScopes={["channel"]}
              />
            ) : !hasSlack ? (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  No Slack workspaces linked. Go to Sources to connect Slack.
                </AlertDescription>
              </Alert>
            ) : (
              <p className="text-sm text-muted-foreground">Select a workspace to see channels</p>
            )}
          </div>
        ) : (
          <ScopeSelector
            value={scopeValue}
            onChange={handleScopeChange}
            channels={guild?.channels || []}
            categories={guild?.categories || []}
          />
        )}
      </div>

      {/* ADR-094: Split Mode for Multi-Channel Summaries */}
      {state.platform === "discord" && (state.scope === "category" || state.scope === "guild") && (
        <div>
          <Label className="text-sm font-medium">Summary splitting</Label>
          <p className="text-xs text-muted-foreground mb-2">
            How should summaries be generated for multiple channels?
          </p>
          <Select
            value={state.splitMode}
            onValueChange={(value: SplitMode) => onChange({ splitMode: value })}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="by-channel">
                <div className="flex flex-col items-start">
                  <span>Separate per channel</span>
                  <span className="text-xs text-muted-foreground">Each channel gets its own focused summary</span>
                </div>
              </SelectItem>
              {state.scope === "guild" && (
                <SelectItem value="by-category">
                  <div className="flex flex-col items-start">
                    <span>Separate per category</span>
                    <span className="text-xs text-muted-foreground">One summary per Discord category</span>
                  </div>
                </SelectItem>
              )}
              <SelectItem value="consolidated">
                <div className="flex flex-col items-start">
                  <span>Single combined summary</span>
                  <span className="text-xs text-muted-foreground">All channels merged into one summary</span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {/* ADR-046: Privacy Warning for Private Channels */}
      {state.platform === "discord" && privacyWarnings.length > 0 && (
        <Alert variant="default" className="border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <AlertTitle className="text-amber-800 dark:text-amber-200">Privacy Notice</AlertTitle>
          <AlertDescription className="text-amber-700 dark:text-amber-300">
            This schedule includes {privacyWarnings.length} private channel{privacyWarnings.length > 1 ? "s" : ""}.
            Summaries will be visible to all guild members in the dashboard.
            <ul className="mt-2 list-disc list-inside text-sm">
              {privacyWarnings.map((w) => (
                <li key={w.channel_id}>#{w.channel_name}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {/* Validation */}
      {state.scope === "channel" && state.channelIds.length === 0 && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Select at least one {state.platform === "whatsapp" ? "chat" : "channel"} to continue
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
