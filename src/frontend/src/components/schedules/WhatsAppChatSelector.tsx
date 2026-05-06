/**
 * WhatsApp Chat Selector for Schedule Creation (ADR-088)
 *
 * Displays imported WhatsApp chats and allows multi-selection
 * for scheduled summaries.
 */

import { useWhatsAppChats, type WhatsAppChat } from "@/hooks/useWhatsApp";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertCircle, MessageSquare, Users, Calendar } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { format } from "date-fns";

interface WhatsAppChatSelectorProps {
  guildId: string;
  selectedChatIds: string[];
  onChange: (chatIds: string[]) => void;
}

export function WhatsAppChatSelector({
  guildId,
  selectedChatIds,
  onChange,
}: WhatsAppChatSelectorProps) {
  const { data: chats, isLoading, error } = useWhatsAppChats(guildId);

  const toggleChat = (chatId: string) => {
    if (selectedChatIds.includes(chatId)) {
      onChange(selectedChatIds.filter((id) => id !== chatId));
    } else {
      onChange([...selectedChatIds, chatId]);
    }
  };

  const selectAll = () => {
    if (chats) {
      onChange(chats.map((c) => c.chat_id));
    }
  };

  const selectNone = () => {
    onChange([]);
  };

  if (isLoading) {
    return (
      <div className="space-y-2">
        <label className="text-sm font-medium">WhatsApp Chats</label>
        <div className="space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Failed to load WhatsApp chats. Make sure you have imported chats first.
        </AlertDescription>
      </Alert>
    );
  }

  if (!chats || chats.length === 0) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          No WhatsApp chats found. Import WhatsApp chat exports first from the
          WhatsApp Imports page.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium">WhatsApp Chats</label>
        <div className="flex gap-2 text-xs">
          <button
            type="button"
            onClick={selectAll}
            className="text-primary hover:underline"
          >
            Select all
          </button>
          <span className="text-muted-foreground">|</span>
          <button
            type="button"
            onClick={selectNone}
            className="text-primary hover:underline"
          >
            Clear
          </button>
        </div>
      </div>

      <ScrollArea className="h-48 rounded-md border">
        <div className="p-2 space-y-1">
          {chats.map((chat) => (
            <ChatItem
              key={chat.chat_id}
              chat={chat}
              selected={selectedChatIds.includes(chat.chat_id)}
              onToggle={() => toggleChat(chat.chat_id)}
            />
          ))}
        </div>
      </ScrollArea>

      <p className="text-xs text-muted-foreground">
        {selectedChatIds.length === 0
          ? "Select at least one chat to summarize"
          : `${selectedChatIds.length} chat${selectedChatIds.length > 1 ? "s" : ""} selected`}
      </p>
    </div>
  );
}

interface ChatItemProps {
  chat: WhatsAppChat;
  selected: boolean;
  onToggle: () => void;
}

function ChatItem({ chat, selected, onToggle }: ChatItemProps) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "—";
    try {
      return format(new Date(dateStr), "MMM d, yyyy");
    } catch {
      return "—";
    }
  };

  return (
    <div
      className={`flex items-start gap-3 p-2 rounded-md cursor-pointer transition-colors ${
        selected ? "bg-primary/10" : "hover:bg-muted/50"
      }`}
      onClick={onToggle}
    >
      <Checkbox checked={selected} className="mt-1" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate">{chat.chat_name}</span>
          {chat.import_count > 1 && (
            <Badge variant="secondary" className="text-xs">
              {chat.import_count} imports
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
          <span className="flex items-center gap-1">
            <MessageSquare className="h-3 w-3" />
            {chat.total_messages.toLocaleString()} msgs
          </span>
          {chat.coverage.earliest && chat.coverage.latest && (
            <span className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {formatDate(chat.coverage.earliest)} — {formatDate(chat.coverage.latest)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
