/**
 * Report Issue Button (ADR-070)
 *
 * Floating button or menu item to trigger issue reporting.
 */

import { useState } from "react";
import { useParams } from "react-router-dom";
import { Bug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ReportIssueDialog } from "./ReportIssueDialog";

interface ReportIssueButtonProps {
  variant?: "default" | "ghost" | "outline";
  size?: "default" | "sm" | "lg" | "icon";
  className?: string;
}

export function ReportIssueButton({
  variant = "ghost",
  size = "sm",
  className,
}: ReportIssueButtonProps) {
  const [open, setOpen] = useState(false);
  const { id: guildId } = useParams<{ id: string }>();

  return (
    <>
      <Button
        variant={variant}
        size={size}
        onClick={() => setOpen(true)}
        className={className}
      >
        <Bug className="h-4 w-4 mr-1" />
        Report Issue
      </Button>
      <ReportIssueDialog
        open={open}
        onClose={() => setOpen(false)}
        guildId={guildId}
      />
    </>
  );
}

// Compact version for menus
export function ReportIssueMenuItem({ onSelect }: { onSelect?: () => void }) {
  const [open, setOpen] = useState(false);
  const { id: guildId } = useParams<{ id: string }>();

  const handleClick = () => {
    setOpen(true);
    onSelect?.();
  };

  return (
    <>
      <button
        onClick={handleClick}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-sm hover:bg-accent rounded-sm"
      >
        <Bug className="h-4 w-4" />
        Report Issue
      </button>
      <ReportIssueDialog
        open={open}
        onClose={() => setOpen(false)}
        guildId={guildId}
      />
    </>
  );
}
