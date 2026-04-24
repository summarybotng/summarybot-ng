/**
 * Shared Summary Actions Component
 *
 * Provides consistent actions for summaries across card and detail views.
 * Any new action added here will appear in both places.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Send,
  MessageCircle,
  Mail,
  RefreshCw,
  Pin,
  Archive,
  Trash2,
  Eye,
  MoreVertical,
  ChevronDown,
} from "lucide-react";

export interface SummaryActionHandlers {
  onView?: () => void;
  onPush: () => void;
  onPushDM: () => void;  // ADR-047: Push to Discord DM
  onEmail: () => void;
  onRegenerate?: () => void;
  onPin: () => void;
  onArchive: () => void;
  onDelete: () => void;
}

export interface SummaryActionState {
  isPinned: boolean;
  isArchived: boolean;
  isRegenerating?: boolean;
}

interface SummaryActionsProps {
  handlers: SummaryActionHandlers;
  state: SummaryActionState;
  /** "dropdown" for compact card view, "buttons" for expanded detail view */
  variant: "dropdown" | "buttons";
  /** Stop event propagation (useful when inside clickable cards) */
  stopPropagation?: boolean;
}

export function SummaryActions({
  handlers,
  state,
  variant,
  stopPropagation = false,
}: SummaryActionsProps) {
  const handleClick = (handler: () => void) => (e: React.MouseEvent) => {
    if (stopPropagation) {
      e.stopPropagation();
    }
    handler();
  };

  if (variant === "dropdown") {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild onClick={(e) => stopPropagation && e.stopPropagation()}>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {handlers.onView && (
            <DropdownMenuItem onClick={handleClick(handlers.onView)}>
              <Eye className="mr-2 h-4 w-4" />
              View Details
            </DropdownMenuItem>
          )}
          <DropdownMenuItem onClick={handleClick(handlers.onPush)}>
            <Send className="mr-2 h-4 w-4" />
            Push to Channel
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleClick(handlers.onPushDM)}>
            <MessageCircle className="mr-2 h-4 w-4" />
            Push to DM
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleClick(handlers.onEmail)}>
            <Mail className="mr-2 h-4 w-4" />
            Send to Email
          </DropdownMenuItem>
          {handlers.onRegenerate && (
            <DropdownMenuItem onClick={handleClick(handlers.onRegenerate)}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Regenerate
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleClick(handlers.onPin)}>
            <Pin className={`mr-2 h-4 w-4 ${state.isPinned ? 'fill-current' : ''}`} />
            {state.isPinned ? "Unpin" : "Pin"}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleClick(handlers.onArchive)}>
            <Archive className="mr-2 h-4 w-4" />
            {state.isArchived ? "Unarchive" : "Archive"}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={handleClick(handlers.onDelete)}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  // Buttons variant for detail view
  return (
    <div className="flex flex-wrap gap-2">
      <Button onClick={handleClick(handlers.onPush)} className="w-full sm:w-auto">
        <Send className="mr-2 h-4 w-4" />
        Push to Channel
      </Button>
      <Button variant="outline" onClick={handleClick(handlers.onPushDM)} className="w-full sm:w-auto">
        <MessageCircle className="mr-2 h-4 w-4" />
        Push to DM
      </Button>
      <Button variant="outline" onClick={handleClick(handlers.onEmail)} className="w-full sm:w-auto">
        <Mail className="mr-2 h-4 w-4" />
        Send to Email
      </Button>
      {handlers.onRegenerate && (
        <Button
          variant="outline"
          onClick={handleClick(handlers.onRegenerate)}
          disabled={state.isRegenerating}
          className="w-full sm:w-auto"
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${state.isRegenerating ? 'animate-spin' : ''}`} />
          {state.isRegenerating ? 'Regenerating...' : 'Regenerate'}
          <ChevronDown className="ml-1 h-3 w-3" />
        </Button>
      )}
      <Button
        variant="outline"
        onClick={handleClick(handlers.onPin)}
        className="w-full sm:w-auto"
      >
        <Pin className={`mr-2 h-4 w-4 ${state.isPinned ? 'fill-current' : ''}`} />
        {state.isPinned ? 'Unpin' : 'Pin'}
      </Button>
      <Button
        variant="outline"
        onClick={handleClick(handlers.onArchive)}
        className="w-full sm:w-auto"
      >
        <Archive className="mr-2 h-4 w-4" />
        {state.isArchived ? 'Unarchive' : 'Archive'}
      </Button>
      <Button
        variant="outline"
        onClick={handleClick(handlers.onDelete)}
        className="w-full sm:w-auto text-destructive hover:text-destructive"
      >
        <Trash2 className="mr-2 h-4 w-4" />
        Delete
      </Button>
    </div>
  );
}
