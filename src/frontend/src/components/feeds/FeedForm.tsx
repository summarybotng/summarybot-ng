/**
 * Feed Form Component (ADR-037)
 *
 * Form for creating and editing RSS/Atom feeds with filter criteria support.
 * ADR-037: Extended with full filter criteria for powerful feed filtering.
 */

import { useState } from "react";
import { ChevronDown, ChevronUp, Filter } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
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
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { FilterCriteriaForm, FilterCriteriaSummary } from "@/components/filters";
import type { Channel } from "@/types";
import type { SummaryFilterCriteria } from "@/types/filters";
import { countActiveFilters, getDefaultCriteria } from "@/types/filters";

export interface FeedFormData {
  /** @deprecated Use criteria.channelIds instead */
  channel_id: string | null;
  feed_type: "rss" | "atom";
  is_public: boolean;
  title: string;
  description: string;
  max_items: number;
  include_full_content: boolean;
  /** ADR-037: Filter criteria for feed content */
  criteria: SummaryFilterCriteria;
}

export const initialFeedFormData: FeedFormData = {
  channel_id: null,
  feed_type: "rss",
  is_public: false,
  title: "",
  description: "",
  max_items: 50,
  include_full_content: true,
  criteria: getDefaultCriteria(),
};

interface FeedFormProps {
  formData: FeedFormData;
  onChange: (data: FeedFormData) => void;
  channels?: Channel[];
  isEdit?: boolean;
}

export function FeedForm({ formData, onChange, channels = [], isEdit = false }: FeedFormProps) {
  const [showFilters, setShowFilters] = useState(false);

  const activeFilterCount = countActiveFilters(formData.criteria);

  const updateCriteria = (updates: Partial<SummaryFilterCriteria>) => {
    onChange({
      ...formData,
      criteria: { ...formData.criteria, ...updates },
    });
  };

  // Handle channel selection - updates both legacy field and criteria
  const handleChannelChange = (value: string) => {
    const channelId = value === "all" ? null : value;
    onChange({
      ...formData,
      channel_id: channelId,
      criteria: {
        ...formData.criteria,
        channelIds: channelId ? [channelId] : undefined,
        channelMode: channelId ? "single" : "all",
      },
    });
  };

  return (
    <div className="space-y-4 py-4">
      {/* Channel Selector - only show on create */}
      {!isEdit && (
        <div className="space-y-2">
          <Label htmlFor="channel">Channel</Label>
          <Select
            value={formData.criteria.channelIds?.[0] || formData.channel_id || "all"}
            onValueChange={handleChannelChange}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select channel" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Channels</SelectItem>
              {channels
                .filter((c) => c.type === "text")
                .map((channel) => (
                  <SelectItem key={channel.id} value={channel.id}>
                    #{channel.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Choose a specific channel or include all guild summaries
          </p>
        </div>
      )}

      {/* Feed Type - only show on create */}
      {!isEdit && (
        <div className="space-y-2">
          <Label htmlFor="feed_type">Feed Type</Label>
          <Select
            value={formData.feed_type}
            onValueChange={(value: "rss" | "atom") =>
              onChange({ ...formData, feed_type: value })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="rss">RSS 2.0</SelectItem>
              <SelectItem value="atom">Atom 1.0</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Title */}
      <div className="space-y-2">
        <Label htmlFor="title">Title</Label>
        <Input
          id="title"
          placeholder="My Server Summaries"
          value={formData.title}
          onChange={(e) => onChange({ ...formData, title: e.target.value })}
        />
      </div>

      {/* Description */}
      <div className="space-y-2">
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          placeholder="AI-generated summaries from my Discord server"
          value={formData.description}
          onChange={(e) => onChange({ ...formData, description: e.target.value })}
          rows={2}
        />
      </div>

      {/* Public Toggle */}
      <div className="flex items-center justify-between rounded-lg border border-border p-3">
        <div className="space-y-0.5">
          <Label htmlFor="is_public">Public Feed</Label>
          <p className="text-xs text-muted-foreground">
            Public feeds don't require authentication
          </p>
        </div>
        <Switch
          id="is_public"
          checked={formData.is_public}
          onCheckedChange={(checked) => onChange({ ...formData, is_public: checked })}
        />
      </div>

      {/* ADR-037: Filter Criteria Section */}
      <Collapsible open={showFilters} onOpenChange={setShowFilters}>
        <CollapsibleTrigger asChild>
          <Button
            variant="outline"
            className="w-full justify-between"
            type="button"
          >
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4" />
              <span>Filter Criteria</span>
              {activeFilterCount > 0 && (
                <Badge variant="secondary" className="ml-2">
                  {activeFilterCount} active
                </Badge>
              )}
            </div>
            {showFilters ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-4">
          <div className="rounded-lg border border-border p-4 space-y-4">
            <p className="text-sm text-muted-foreground">
              Filter which summaries appear in this feed. Leave empty to include all summaries.
            </p>

            <FilterCriteriaForm
              criteria={formData.criteria}
              onChange={(criteria) => onChange({ ...formData, criteria })}
              channels={channels}
              compact
              label=""
            />

            {activeFilterCount > 0 && (
              <div className="pt-2 border-t">
                <FilterCriteriaSummary
                  criteria={formData.criteria}
                  onUpdate={updateCriteria}
                  compact
                />
              </div>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Max Items */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Max Items</Label>
          <span className="text-sm text-muted-foreground">{formData.max_items}</span>
        </div>
        <Slider
          value={[formData.max_items]}
          onValueChange={([value]) => onChange({ ...formData, max_items: value })}
          min={1}
          max={100}
          step={1}
        />
        <p className="text-xs text-muted-foreground">
          Number of summaries to include in the feed (1-100)
        </p>
      </div>

      {/* Include Full Content */}
      <div className="flex items-center justify-between rounded-lg border border-border p-3">
        <div className="space-y-0.5">
          <Label htmlFor="include_full_content">Include Full Content</Label>
          <p className="text-xs text-muted-foreground">
            Include the complete summary text in feed items
          </p>
        </div>
        <Switch
          id="include_full_content"
          checked={formData.include_full_content}
          onCheckedChange={(checked) =>
            onChange({ ...formData, include_full_content: checked })
          }
        />
      </div>
    </div>
  );
}
