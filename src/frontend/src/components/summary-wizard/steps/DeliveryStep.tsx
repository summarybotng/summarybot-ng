/**
 * Step 3: Delivery & Options (ADR-089)
 *
 * Only shown for recurring schedules.
 * Configures where summaries are delivered + advanced options.
 */

import { useState } from "react";
import { useGuild } from "@/hooks/useGuilds";
import { usePromptTemplates } from "@/hooks/usePromptTemplates";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, Mail, Webhook, Hash, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StepProps } from "../types";

export function DeliveryStep({ state, onChange, guildId }: StepProps) {
  const { data: guild } = useGuild(guildId);
  const { data: promptTemplates } = usePromptTemplates(guildId);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const textChannels = guild?.channels.filter((c) => c.type === "text") || [];

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-medium">Where should we deliver each summary?</h3>

      {/* Destinations */}
      <div className="space-y-4">
        {/* Dashboard - always on */}
        <div className="flex items-center gap-3 p-3 rounded-md border bg-muted/30">
          <Checkbox checked disabled />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4" />
              <span className="font-medium">Dashboard</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Always saved to your summaries dashboard
            </p>
          </div>
        </div>

        {/* Discord Channel */}
        <div className="flex items-start gap-3 p-3 rounded-md border">
          <Checkbox
            checked={state.destinations.discordChannel}
            onCheckedChange={(checked) =>
              onChange({
                destinations: {
                  ...state.destinations,
                  discordChannel: !!checked,
                },
              })
            }
            className="mt-1"
          />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <Hash className="h-4 w-4" />
              <span className="font-medium">Post to Discord channel</span>
            </div>
            {state.destinations.discordChannel && (
              <Select
                value={state.destinations.discordChannelId}
                onValueChange={(v) =>
                  onChange({
                    destinations: {
                      ...state.destinations,
                      discordChannelId: v,
                    },
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select channel" />
                </SelectTrigger>
                <SelectContent>
                  {textChannels.map((ch) => (
                    <SelectItem key={ch.id} value={ch.id}>
                      #{ch.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        </div>

        {/* Webhook */}
        <div className="flex items-start gap-3 p-3 rounded-md border">
          <Checkbox
            checked={state.destinations.webhook}
            onCheckedChange={(checked) =>
              onChange({
                destinations: {
                  ...state.destinations,
                  webhook: !!checked,
                },
              })
            }
            className="mt-1"
          />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <Webhook className="h-4 w-4" />
              <span className="font-medium">Send to webhook</span>
            </div>
            {state.destinations.webhook && (
              <Input
                type="url"
                placeholder="https://..."
                value={state.destinations.webhookUrl}
                onChange={(e) =>
                  onChange({
                    destinations: {
                      ...state.destinations,
                      webhookUrl: e.target.value,
                    },
                  })
                }
              />
            )}
          </div>
        </div>

        {/* Email */}
        <div className="flex items-start gap-3 p-3 rounded-md border">
          <Checkbox
            checked={state.destinations.email}
            onCheckedChange={(checked) =>
              onChange({
                destinations: {
                  ...state.destinations,
                  email: !!checked,
                },
              })
            }
            className="mt-1"
          />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4" />
              <span className="font-medium">Email</span>
            </div>
            {state.destinations.email && (
              <Input
                type="text"
                placeholder="email@example.com, another@example.com"
                value={state.destinations.emailAddresses}
                onChange={(e) =>
                  onChange({
                    destinations: {
                      ...state.destinations,
                      emailAddresses: e.target.value,
                    },
                  })
                }
              />
            )}
          </div>
        </div>
      </div>

      {/* Advanced Options */}
      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", advancedOpen && "rotate-180")}
          />
          Advanced options
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-4 space-y-4">
          {/* Summary Length */}
          <div>
            <Label>Summary length</Label>
            <Select
              value={state.summaryLength}
              onValueChange={(v) =>
                onChange({ summaryLength: v as "brief" | "detailed" | "comprehensive" })
              }
            >
              <SelectTrigger className="mt-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="brief">Brief</SelectItem>
                <SelectItem value="detailed">Detailed</SelectItem>
                <SelectItem value="comprehensive">Comprehensive</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Perspective / Template */}
          <div>
            <Label>Perspective</Label>
            <Select
              value={state.promptTemplateId || state.perspective}
              onValueChange={(v) => {
                if (v.startsWith("template:")) {
                  onChange({
                    promptTemplateId: v.replace("template:", ""),
                    perspective: "general",
                  });
                } else {
                  onChange({ perspective: v, promptTemplateId: null });
                }
              }}
            >
              <SelectTrigger className="mt-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="general">General</SelectItem>
                <SelectItem value="technical">Technical</SelectItem>
                <SelectItem value="executive">Executive</SelectItem>
                <SelectItem value="action-focused">Action-Focused</SelectItem>
                {promptTemplates && promptTemplates.length > 0 && (
                  <>
                    <div className="px-2 py-1.5 text-xs text-muted-foreground">
                      Custom Templates
                    </div>
                    {promptTemplates.map((t) => (
                      <SelectItem key={t.id} value={`template:${t.id}`}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </>
                )}
              </SelectContent>
            </Select>
          </div>

          {/* Min Messages */}
          <div>
            <Label>Minimum messages</Label>
            <Input
              type="number"
              min={1}
              max={100}
              value={state.minMessages}
              onChange={(e) => onChange({ minMessages: parseInt(e.target.value) || 5 })}
              className="mt-2 w-24"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Skip summary if fewer messages in period
            </p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
