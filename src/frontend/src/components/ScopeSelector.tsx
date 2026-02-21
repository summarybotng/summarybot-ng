/**
 * ScopeSelector Component (ADR-011)
 *
 * Reusable component for selecting summary scope (channel, category, or guild/server).
 * Used in both real-time summaries and scheduled summaries.
 */

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Hash, FolderOpen, Server, Search } from "lucide-react";
import { useState, useMemo } from "react";
import type { Channel, Category } from "@/types";

export type ScopeType = "channel" | "category" | "guild";

export interface ScopeSelectorValue {
  scope: ScopeType;
  channelIds: string[];
  categoryId: string;
}

interface ScopeSelectorProps {
  value: ScopeSelectorValue;
  onChange: (value: ScopeSelectorValue) => void;
  channels: Channel[];
  categories: Category[];
  /** Optional label to show above the scope buttons */
  label?: string;
  /** Hide the scope type buttons (for cases where scope is fixed) */
  hideScopeButtons?: boolean;
  /** Restrict available scope types */
  allowedScopes?: ScopeType[];
  /** Compact mode for smaller containers */
  compact?: boolean;
}

export function ScopeSelector({
  value,
  onChange,
  channels,
  categories,
  label = "Scope",
  hideScopeButtons = false,
  allowedScopes = ["channel", "category", "guild"],
  compact = false,
}: ScopeSelectorProps) {
  const [channelSearch, setChannelSearch] = useState("");

  const textChannels = useMemo(
    () => channels.filter((c) => c.type === "text"),
    [channels]
  );

  const filteredChannels = useMemo(
    () =>
      textChannels.filter((c) =>
        c.name.toLowerCase().includes(channelSearch.toLowerCase())
      ),
    [textChannels, channelSearch]
  );

  const handleScopeChange = (newScope: ScopeType) => {
    onChange({
      ...value,
      scope: newScope,
      // Reset selections when scope changes
      channelIds: [],
      categoryId: "",
    });
  };

  const handleChannelToggle = (channelId: string, checked: boolean) => {
    if (checked) {
      onChange({
        ...value,
        channelIds: [...value.channelIds, channelId],
      });
    } else {
      onChange({
        ...value,
        channelIds: value.channelIds.filter((id) => id !== channelId),
      });
    }
  };

  const handleCategoryChange = (categoryId: string) => {
    onChange({
      ...value,
      categoryId,
    });
  };

  return (
    <div className="space-y-4">
      {/* Scope Type Buttons */}
      {!hideScopeButtons && (
        <div className="space-y-2">
          <label className="text-sm font-medium">{label}</label>
          <div className={`grid gap-2 ${compact ? "grid-cols-3" : "grid-cols-3"}`}>
            {allowedScopes.includes("channel") && (
              <Button
                type="button"
                variant={value.scope === "channel" ? "default" : "outline"}
                size="sm"
                className="w-full"
                onClick={() => handleScopeChange("channel")}
              >
                <Hash className="mr-1.5 h-3.5 w-3.5" />
                Channel
              </Button>
            )}
            {allowedScopes.includes("category") && (
              <Button
                type="button"
                variant={value.scope === "category" ? "default" : "outline"}
                size="sm"
                className="w-full"
                onClick={() => handleScopeChange("category")}
              >
                <FolderOpen className="mr-1.5 h-3.5 w-3.5" />
                Category
              </Button>
            )}
            {allowedScopes.includes("guild") && (
              <Button
                type="button"
                variant={value.scope === "guild" ? "default" : "outline"}
                size="sm"
                className="w-full"
                onClick={() => handleScopeChange("guild")}
              >
                <Server className="mr-1.5 h-3.5 w-3.5" />
                Server
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Channel Selection - shown when scope is "channel" */}
      {value.scope === "channel" && (
        <div className="space-y-2">
          <label className="text-sm font-medium">Channels</label>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search channels..."
              value={channelSearch}
              onChange={(e) => setChannelSearch(e.target.value)}
              className="pl-8"
            />
          </div>
          <div
            className={`space-y-2 overflow-y-auto rounded-md border p-3 ${
              compact ? "max-h-32" : "max-h-40"
            }`}
          >
            {filteredChannels.map((channel) => (
              <div key={channel.id} className="flex items-center space-x-2">
                <Checkbox
                  id={`scope-channel-${channel.id}`}
                  checked={value.channelIds.includes(channel.id)}
                  onCheckedChange={(checked) =>
                    handleChannelToggle(channel.id, checked as boolean)
                  }
                />
                <label
                  htmlFor={`scope-channel-${channel.id}`}
                  className="text-sm cursor-pointer"
                >
                  #{channel.name}
                </label>
              </div>
            ))}
            {filteredChannels.length === 0 && (
              <p className="text-sm text-muted-foreground py-2 text-center">
                {channelSearch
                  ? `No channels match "${channelSearch}"`
                  : "No text channels available"}
              </p>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {value.channelIds.length === 0
              ? "All enabled channels will be included"
              : `${value.channelIds.length} channel(s) selected`}
          </p>
        </div>
      )}

      {/* Category Selection - shown when scope is "category" */}
      {value.scope === "category" && (
        <div className="space-y-2">
          <label className="text-sm font-medium">Category</label>
          <Select value={value.categoryId} onValueChange={handleCategoryChange}>
            <SelectTrigger>
              <SelectValue placeholder="Select a category" />
            </SelectTrigger>
            <SelectContent>
              {categories.map((category) => (
                <SelectItem key={category.id} value={category.id}>
                  {category.name} ({category.channel_count} channels)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {categories.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No categories available
            </p>
          )}
        </div>
      )}

      {/* Guild/Server scope info */}
      {value.scope === "guild" && (
        <div className="rounded-md border border-primary/20 bg-primary/5 p-3">
          <p className="text-sm text-muted-foreground">
            All enabled channels across the server will be summarized.
          </p>
        </div>
      )}
    </div>
  );
}

// Helper to create initial scope value
export function getInitialScopeValue(scope: ScopeType = "channel"): ScopeSelectorValue {
  return {
    scope,
    channelIds: [],
    categoryId: "",
  };
}

export default ScopeSelector;
