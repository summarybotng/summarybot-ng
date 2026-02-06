import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Channel } from "@/types";

export interface FeedFormData {
  channel_id: string | null;
  feed_type: "rss" | "atom";
  is_public: boolean;
  title: string;
  description: string;
  max_items: number;
  include_full_content: boolean;
}

export const initialFeedFormData: FeedFormData = {
  channel_id: null,
  feed_type: "rss",
  is_public: false,
  title: "",
  description: "",
  max_items: 50,
  include_full_content: true,
};

interface FeedFormProps {
  formData: FeedFormData;
  onChange: (data: FeedFormData) => void;
  channels?: Channel[];
  isEdit?: boolean;
}

export function FeedForm({ formData, onChange, channels = [], isEdit = false }: FeedFormProps) {
  return (
    <div className="space-y-4 py-4">
      {/* Channel Selector - only show on create */}
      {!isEdit && (
        <div className="space-y-2">
          <Label htmlFor="channel">Channel</Label>
          <Select
            value={formData.channel_id || "all"}
            onValueChange={(value) =>
              onChange({ ...formData, channel_id: value === "all" ? null : value })
            }
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
