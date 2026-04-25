/**
 * Push to DM Modal (ADR-047)
 *
 * Send a stored summary directly to a Discord user via DM.
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
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, Send, MessageCircle, AlertCircle } from "lucide-react";
import type { PushToDMRequest } from "@/types";

// Helper to get/set last used user ID per guild
const getLastDMUserId = (guildId: string): string | null => {
  try {
    return localStorage.getItem(`dm_user_${guildId}`);
  } catch {
    return null;
  }
};

const setLastDMUserId = (guildId: string, userId: string) => {
  try {
    localStorage.setItem(`dm_user_${guildId}`, userId);
  } catch {
    // Ignore localStorage errors
  }
};

interface PushToDMModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summaryTitle: string;
  isPending: boolean;
  onSubmit: (request: PushToDMRequest) => void;
  guildId: string;
  error?: string | null;
  /** Current user's Discord ID - used as default when no previous ID stored */
  currentUserId?: string;
}

export function PushToDMModal({
  open,
  onOpenChange,
  summaryTitle,
  isPending,
  onSubmit,
  guildId,
  error,
  currentUserId,
}: PushToDMModalProps) {
  // Default to: 1) last used ID, 2) current user's ID, 3) empty
  const [userId, setUserId] = useState(() => getLastDMUserId(guildId) || currentUserId || "");
  const [format, setFormat] = useState<"embed" | "markdown" | "plain">("embed");
  const [includeReferences, setIncludeReferences] = useState(true);
  const [customMessage, setCustomMessage] = useState("");
  // Section toggles
  const [includeKeyPoints, setIncludeKeyPoints] = useState(true);
  const [includeActionItems, setIncludeActionItems] = useState(true);
  const [includeParticipants, setIncludeParticipants] = useState(true);
  const [includeTechnicalTerms, setIncludeTechnicalTerms] = useState(true);

  // Validate Discord user ID format (snowflake: 17-19 digits)
  const isValidUserId = /^\d{17,19}$/.test(userId.trim());

  const handleSubmit = () => {
    if (!isValidUserId) return;

    // Save the user ID as the default for next time
    setLastDMUserId(guildId, userId.trim());

    onSubmit({
      user_id: userId.trim(),
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
      // Reset form on close (except userId which persists)
      setFormat("embed");
      setIncludeReferences(true);
      setCustomMessage("");
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
          <DialogTitle className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5" />
            Push to DM
          </DialogTitle>
          <DialogDescription>
            Send "{summaryTitle}" directly to a Discord user
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Error Alert */}
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* User ID Input */}
          <div className="space-y-2">
            <Label htmlFor="user-id">Discord User ID</Label>
            <Input
              id="user-id"
              placeholder="Enter Discord user ID (e.g., 123456789012345678)"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className={userId && !isValidUserId ? "border-destructive" : ""}
            />
            {userId && !isValidUserId && (
              <p className="text-xs text-destructive">
                User ID must be 17-19 digits (Discord snowflake format)
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              Right-click a user in Discord and select "Copy User ID" (requires Developer Mode)
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
              id="include-refs-dm"
              checked={includeReferences}
              onCheckedChange={(checked) =>
                setIncludeReferences(checked as boolean)
              }
            />
            <label htmlFor="include-refs-dm" className="text-sm cursor-pointer">
              Include source references
            </label>
          </div>

          {/* Section Toggles */}
          <div className="space-y-2">
            <Label>Sections to Include</Label>
            <div className="rounded-md border p-3 space-y-2">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="dm-include-key-points"
                  checked={includeKeyPoints}
                  onCheckedChange={(checked) =>
                    setIncludeKeyPoints(checked as boolean)
                  }
                />
                <label htmlFor="dm-include-key-points" className="text-sm cursor-pointer">
                  Key Points
                </label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="dm-include-action-items"
                  checked={includeActionItems}
                  onCheckedChange={(checked) =>
                    setIncludeActionItems(checked as boolean)
                  }
                />
                <label htmlFor="dm-include-action-items" className="text-sm cursor-pointer">
                  Action Items
                </label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="dm-include-participants"
                  checked={includeParticipants}
                  onCheckedChange={(checked) =>
                    setIncludeParticipants(checked as boolean)
                  }
                />
                <label htmlFor="dm-include-participants" className="text-sm cursor-pointer">
                  Participants
                </label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="dm-include-technical-terms"
                  checked={includeTechnicalTerms}
                  onCheckedChange={(checked) =>
                    setIncludeTechnicalTerms(checked as boolean)
                  }
                />
                <label htmlFor="dm-include-technical-terms" className="text-sm cursor-pointer">
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
            disabled={!isValidUserId || isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Sending...
              </>
            ) : (
              <>
                <Send className="mr-2 h-4 w-4" />
                Send DM
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
