/**
 * When Type Selection Card (ADR-089)
 */

import { cn } from "@/lib/utils";
import type { WhenType } from "../types";

interface WhenTypeCardProps {
  whenType: WhenType;
  selected: boolean;
  onClick: () => void;
}

const whenTypeConfig: Record<WhenType, { icon: string; label: string; description: string }> = {
  now: {
    icon: "⚡",
    label: "Now",
    description: "Last few hours",
  },
  recurring: {
    icon: "🔄",
    label: "Recurring",
    description: "Schedule it",
  },
  past: {
    icon: "📅",
    label: "Past",
    description: "Specific dates",
  },
};

export function WhenTypeCard({ whenType, selected, onClick }: WhenTypeCardProps) {
  const config = whenTypeConfig[whenType];

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-center justify-center p-4 rounded-lg border-2 transition-all",
        "hover:border-primary/50 hover:bg-muted/50",
        "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
        selected && "border-primary bg-primary/10",
        !selected && "border-muted"
      )}
    >
      <span className="text-3xl mb-2">{config.icon}</span>
      <span className="font-medium">{config.label}</span>
      <span className="text-xs text-muted-foreground">{config.description}</span>
    </button>
  );
}
