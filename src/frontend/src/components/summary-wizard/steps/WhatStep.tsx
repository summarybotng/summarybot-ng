/**
 * Step 1: What to Summarize (ADR-089)
 *
 * Platform selection + channel/scope selection
 */

import { useGuild } from "@/hooks/useGuilds";
import { useWhatsAppChats } from "@/hooks/useWhatsApp";
import { PlatformCard } from "../shared/PlatformCard";
import { ScopeSelector, type ScopeSelectorValue } from "@/components/ScopeSelector";
import { WhatsAppChatSelector } from "@/components/schedules/WhatsAppChatSelector";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle } from "lucide-react";
import type { StepProps, Platform } from "../types";

export function WhatStep({ state, onChange, guildId }: StepProps) {
  const { data: guild, isLoading: guildLoading } = useGuild(guildId);
  const { data: whatsappChats } = useWhatsAppChats(guildId);

  const hasWhatsApp = whatsappChats && whatsappChats.length > 0;

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
        ) : (
          <ScopeSelector
            value={scopeValue}
            onChange={handleScopeChange}
            channels={guild?.channels || []}
            categories={guild?.categories || []}
          />
        )}
      </div>

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
