/**
 * Step 3: Where (Delivery & Options) (ADR-089, ADR-099)
 *
 * Available for all wizard modes (now, recurring, past).
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
import { ChevronDown, Mail, Webhook, Hash, MessageSquare, MessageCircle, FileText, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { StepProps } from "../types";

export function WhereStep({ state, onChange, guildId }: StepProps) {
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

        {/* Discord DM (ADR-047) */}
        <div className="flex items-start gap-3 p-3 rounded-md border">
          <Checkbox
            checked={state.destinations.discordDm}
            onCheckedChange={(checked) =>
              onChange({
                destinations: {
                  ...state.destinations,
                  discordDm: !!checked,
                },
              })
            }
            className="mt-1"
          />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <MessageCircle className="h-4 w-4" />
              <span className="font-medium">Discord DM</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Send directly to a user via DM
            </p>
            {state.destinations.discordDm && (
              <Input
                placeholder="Discord User ID (e.g., 123456789012345678)"
                value={state.destinations.discordDmUserId}
                onChange={(e) =>
                  onChange({
                    destinations: {
                      ...state.destinations,
                      discordDmUserId: e.target.value,
                    },
                  })
                }
              />
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

        {/* Confluence (ADR-099) */}
        <div className="flex items-start gap-3 p-3 rounded-md border">
          <Checkbox
            checked={state.destinations.confluence}
            onCheckedChange={(checked) =>
              onChange({
                destinations: {
                  ...state.destinations,
                  confluence: !!checked,
                },
              })
            }
            className="mt-1"
          />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4" />
              <span className="font-medium">Publish to Confluence</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Create a Confluence page with the summary content
            </p>
            {state.destinations.confluence && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Label htmlFor="pageTitle" className="text-sm">
                    Page title template
                  </Label>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="right" className="max-w-xs">
                        <p className="text-xs">
                          Available variables:<br />
                          <code>{"{channels}"}</code> - Channel names<br />
                          <code>{"{date}"}</code> - Summary date<br />
                          <code>{"{week}"}</code> - Week number<br />
                          <code>{"{guild}"}</code> - Server name
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
                <Input
                  id="pageTitle"
                  placeholder="{channels} Summary - {date}"
                  value={state.pageTitleTemplate}
                  onChange={(e) => onChange({ pageTitleTemplate: e.target.value })}
                />
              </div>
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
                <SelectItem value="developer">Developer</SelectItem>
                <SelectItem value="marketing">Marketing</SelectItem>
                <SelectItem value="executive">Executive</SelectItem>
                <SelectItem value="support">Support</SelectItem>
                {promptTemplates && promptTemplates.length > 0 && (
                  <>
                    <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground border-t mt-1 pt-2">
                      Custom Perspectives
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
