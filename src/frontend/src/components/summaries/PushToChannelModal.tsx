/**
 * Push to Channel Modal (ADR-005)
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Send, Search } from "lucide-react";
import type { Channel, PushToChannelRequest } from "@/types";

interface PushToChannelModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  channels: Channel[];
  summaryTitle: string;
  isPending: boolean;
  onSubmit: (request: PushToChannelRequest) => void;
}

export function PushToChannelModal({
  open,
  onOpenChange,
  channels,
  summaryTitle,
  isPending,
  onSubmit,
}: PushToChannelModalProps) {
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [format, setFormat] = useState<"embed" | "markdown" | "plain">("embed");
  const [includeReferences, setIncludeReferences] = useState(true);
  const [customMessage, setCustomMessage] = useState("");
  const [channelSearch, setChannelSearch] = useState("");
  // Section toggles
  const [includeKeyPoints, setIncludeKeyPoints] = useState(true);
  const [includeActionItems, setIncludeActionItems] = useState(true);
  const [includeParticipants, setIncludeParticipants] = useState(true);
  const [includeTechnicalTerms, setIncludeTechnicalTerms] = useState(true);

  const textChannels = channels.filter((c) => c.type === "text");
  const filteredChannels = textChannels.filter((c) =>
    c.name.toLowerCase().includes(channelSearch.toLowerCase())
  );

  const handleSubmit = () => {
    if (selectedChannels.length === 0) return;

    onSubmit({
      channel_ids: selectedChannels,
      format,
      include_references: includeReferences,
      custom_message: customMessage || undefined,
      include_key_points: includeKeyPoints,
      include_action_items: includeActionItems,
      include_participants: includeParticipants,
      include_technical_terms: includeTechnicalTerms,
    });
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      // Reset form on close
      setSelectedChannels([]);
      setFormat("embed");
      setIncludeReferences(true);
      setCustomMessage("");
      setChannelSearch("");
      setIncludeKeyPoints(true);
      setIncludeActionItems(true);
      setIncludeParticipants(true);
      setIncludeTechnicalTerms(true);
    }
    onOpenChange(isOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Push to Channel</DialogTitle>
          <DialogDescription>
            Send "{summaryTitle}" to Discord channels
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Channel Selection */}
          <div className="space-y-2">
            <Label>Channels</Label>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search channels..."
                value={channelSearch}
                onChange={(e) => setChannelSearch(e.target.value)}
                className="pl-8"
              />
            </div>
            <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">
              {filteredChannels.map((channel) => (
                <div key={channel.id} className="flex items-center space-x-2">
                  <Checkbox
                    id={`push-${channel.id}`}
                    checked={selectedChannels.includes(channel.id)}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        setSelectedChannels([...selectedChannels, channel.id]);
                      } else {
                        setSelectedChannels(
                          selectedChannels.filter((id) => id !== channel.id)
                        );
                      }
                    }}
                  />
                  <label
                    htmlFor={`push-${channel.id}`}
                    className="text-sm cursor-pointer"
                  >
                    #{channel.name}
                  </label>
                </div>
              ))}
              {filteredChannels.length === 0 && (
                <p className="text-sm text-muted-foreground py-2 text-center">
                  No channels found
                </p>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {selectedChannels.length} channel(s) selected
            </p>
          </div>

          {/* Format Selection */}
          <div className="space-y-2">
            <Label>Format</Label>
            <Select
              value={format}
              onValueChange={(v) => setFormat(v as typeof format)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="embed">Embed (Recommended)</SelectItem>
                <SelectItem value="markdown">Markdown</SelectItem>
                <SelectItem value="plain">Plain Text</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Include References */}
          <div className="flex items-center space-x-2">
            <Checkbox
              id="include-refs"
              checked={includeReferences}
              onCheckedChange={(checked) =>
                setIncludeReferences(checked as boolean)
              }
            />
            <label htmlFor="include-refs" className="text-sm cursor-pointer">
              Include source references
            </label>
          </div>

          {/* Section Toggles */}
          <div className="space-y-2">
            <Label>Sections to Include</Label>
            <div className="rounded-md border p-3 space-y-2">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="include-key-points"
                  checked={includeKeyPoints}
                  onCheckedChange={(checked) =>
                    setIncludeKeyPoints(checked as boolean)
                  }
                />
                <label htmlFor="include-key-points" className="text-sm cursor-pointer">
                  Key Points
                </label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="include-action-items"
                  checked={includeActionItems}
                  onCheckedChange={(checked) =>
                    setIncludeActionItems(checked as boolean)
                  }
                />
                <label htmlFor="include-action-items" className="text-sm cursor-pointer">
                  Action Items
                </label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="include-participants"
                  checked={includeParticipants}
                  onCheckedChange={(checked) =>
                    setIncludeParticipants(checked as boolean)
                  }
                />
                <label htmlFor="include-participants" className="text-sm cursor-pointer">
                  Participants
                </label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="include-technical-terms"
                  checked={includeTechnicalTerms}
                  onCheckedChange={(checked) =>
                    setIncludeTechnicalTerms(checked as boolean)
                  }
                />
                <label htmlFor="include-technical-terms" className="text-sm cursor-pointer">
                  Technical Terms
                </label>
              </div>
            </div>
          </div>

          {/* Custom Message */}
          <div className="space-y-2">
            <Label>Custom Intro Message (Optional)</Label>
            <Textarea
              placeholder="Add a message to appear before the summary..."
              value={customMessage}
              onChange={(e) => setCustomMessage(e.target.value)}
              rows={2}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={selectedChannels.length === 0 || isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Pushing...
              </>
            ) : (
              <>
                <Send className="mr-2 h-4 w-4" />
                Push Summary
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
