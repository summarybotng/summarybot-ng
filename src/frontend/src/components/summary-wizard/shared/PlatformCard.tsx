/**
 * Platform Selection Card (ADR-089)
 */

import { cn } from "@/lib/utils";
import type { Platform } from "../types";

interface PlatformCardProps {
  platform: Platform;
  selected: boolean;
  onClick: () => void;
  disabled?: boolean;
}

const platformConfig: Record<Platform, { icon: string; label: string; description: string }> = {
  discord: {
    icon: "🎮",
    label: "Discord",
    description: "Server channels",
  },
  slack: {
    icon: "💬",
    label: "Slack",
    description: "Workspace channels",
  },
  whatsapp: {
    icon: "📱",
    label: "WhatsApp",
    description: "Imported chats",
  },
};

export function PlatformCard({ platform, selected, onClick, disabled }: PlatformCardProps) {
  const config = platformConfig[platform];

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex flex-col items-center justify-center p-4 rounded-lg border-2 transition-all",
        "hover:border-primary/50 hover:bg-muted/50",
        "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
        selected && "border-primary bg-primary/10",
        !selected && "border-muted",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      <span className="text-3xl mb-2">{config.icon}</span>
      <span className="font-medium">{config.label}</span>
      <span className="text-xs text-muted-foreground">{config.description}</span>
    </button>
  );
}
