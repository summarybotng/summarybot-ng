import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { useTimezone, parseAsUTC } from "@/contexts/TimezoneContext";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
  DrawerFooter,
} from "@/components/ui/drawer";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  AlertCircle,
  AlertTriangle,
  Info,
  XCircle,
  CheckCircle,
  Hash,
  Loader2,
  Clock,
  Code,
} from "lucide-react";
import { useIsMobile } from "@/hooks/use-mobile";
import type { ErrorLogItem, ErrorSeverity, ErrorType } from "@/types/errors";

interface ErrorDetailDrawerProps {
  error: ErrorLogItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onResolve: (errorId: string, notes?: string) => Promise<void>;
  isResolving: boolean;
}

const severityConfig: Record<
  ErrorSeverity,
  { icon: typeof AlertCircle; color: string; label: string }
> = {
  critical: { icon: XCircle, color: "text-red-500", label: "Critical" },
  error: { icon: AlertCircle, color: "text-orange-500", label: "Error" },
  warning: { icon: AlertTriangle, color: "text-yellow-500", label: "Warning" },
  info: { icon: Info, color: "text-blue-500", label: "Info" },
};

const errorTypeLabels: Record<ErrorType, string> = {
  discord_permission: "Discord Permission",
  discord_not_found: "Discord Not Found",
  discord_rate_limit: "Discord Rate Limit",
  api_error: "API Error",
  database_error: "Database Error",
  summarization_error: "Summarization Error",
  schedule_error: "Schedule Error",
  webhook_error: "Webhook Error",
  unknown: "Unknown Error",
};

export function ErrorDetailDrawer({
  error,
  open,
  onOpenChange,
  onResolve,
  isResolving,
}: ErrorDetailDrawerProps) {
  const isMobile = useIsMobile();
  const { formatDateTime } = useTimezone();
  const [showResolveDialog, setShowResolveDialog] = useState(false);
  const [notes, setNotes] = useState("");

  if (!error) return null;

  const severity = severityConfig[error.severity];
  const SeverityIcon = severity.icon;

  const handleResolve = async () => {
    await onResolve(error.id, notes || undefined);
    setNotes("");
    setShowResolveDialog(false);
    onOpenChange(false);
  };

  const content = (
    <div className="space-y-6">
      {/* Header info */}
      <div className="flex items-start gap-4">
        <div className={cn("flex-shrink-0 mt-1", severity.color)}>
          <SeverityIcon className="h-6 w-6" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <Badge variant="outline">{errorTypeLabels[error.error_type]}</Badge>
            <Badge
              variant={error.is_resolved ? "secondary" : "destructive"}
              className="gap-1"
            >
              {error.is_resolved ? (
                <>
                  <CheckCircle className="h-3 w-3" />
                  Resolved
                </>
              ) : (
                "Unresolved"
              )}
            </Badge>
          </div>
          {error.error_code && (
            <p className="text-xs text-muted-foreground mb-1">
              Code: {error.error_code}
            </p>
          )}
        </div>
      </div>

      {/* Message */}
      <div>
        <Label className="text-xs text-muted-foreground">Message</Label>
        <p className="mt-1 text-sm">{error.message}</p>
      </div>

      {/* Details grid */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label className="text-xs text-muted-foreground">Operation</Label>
          <p className="mt-1 text-sm font-medium">{error.operation}</p>
        </div>
        {error.channel_name && (
          <div>
            <Label className="text-xs text-muted-foreground">Channel</Label>
            <p className="mt-1 text-sm font-medium flex items-center gap-1">
              <Hash className="h-3 w-3" />
              {error.channel_name}
            </p>
          </div>
        )}
        <div>
          <Label className="text-xs text-muted-foreground">Occurred</Label>
          <p className="mt-1 text-sm font-medium flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatDateTime(error.created_at)}
          </p>
          <p className="text-xs text-muted-foreground">
            {formatDistanceToNow(parseAsUTC(error.created_at), { addSuffix: true })}
          </p>
        </div>
        <div>
          <Label className="text-xs text-muted-foreground">Severity</Label>
          <p className={cn("mt-1 text-sm font-medium", severity.color)}>
            {severity.label}
          </p>
        </div>
      </div>

      {/* Additional Details */}
      {error.details && Object.keys(error.details).length > 0 && (
        <div>
          <Label className="text-xs text-muted-foreground">Additional Details</Label>
          <div className="mt-2 rounded-md border bg-muted/50 p-3">
            <dl className="space-y-1 text-sm">
              {Object.entries(error.details).map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <dt className="font-medium text-muted-foreground">{key}:</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}
      {error.stack_trace && (
        <div>
          <Label className="text-xs text-muted-foreground flex items-center gap-1">
            <Code className="h-3 w-3" />
            Stack Trace
          </Label>
          <ScrollArea className="mt-2 h-40 rounded-md border bg-muted/50 p-3">
            <pre className="text-xs font-mono whitespace-pre-wrap">
              {error.stack_trace}
            </pre>
          </ScrollArea>
        </div>
      )}

      {/* Resolution info */}
      {error.is_resolved && (
        <div className="rounded-lg border border-green-500/20 bg-green-500/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="h-4 w-4 text-green-500" />
            <span className="font-medium text-green-500">Resolved</span>
          </div>
          {error.resolved_at && (
            <p className="text-xs text-muted-foreground">
              {formatDateTime(error.resolved_at)}
            </p>
          )}
          {error.resolution_notes && (
            <p className="mt-2 text-sm">{error.resolution_notes}</p>
          )}
        </div>
      )}
    </div>
  );

  const footer = !error.is_resolved && (
    <Button onClick={() => setShowResolveDialog(true)} className="w-full">
      <CheckCircle className="mr-2 h-4 w-4" />
      Mark as Resolved
    </Button>
  );

  // Resolve confirmation dialog
  const resolveDialog = (
    <Dialog open={showResolveDialog} onOpenChange={setShowResolveDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resolve Error</DialogTitle>
          <DialogDescription>
            Mark this error as resolved. You can optionally add notes about how it
            was fixed.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <Label htmlFor="notes">Resolution Notes (optional)</Label>
          <Textarea
            id="notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Describe how this error was resolved..."
            className="mt-2"
            rows={3}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setShowResolveDialog(false)}>
            Cancel
          </Button>
          <Button onClick={handleResolve} disabled={isResolving}>
            {isResolving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Resolve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  if (isMobile) {
    return (
      <>
        <Drawer open={open} onOpenChange={onOpenChange}>
          <DrawerContent>
            <DrawerHeader>
              <DrawerTitle>Error Details</DrawerTitle>
              <DrawerDescription>
                View error information and resolution options
              </DrawerDescription>
            </DrawerHeader>
            <div className="px-4 pb-4">{content}</div>
            {footer && <DrawerFooter>{footer}</DrawerFooter>}
          </DrawerContent>
        </Drawer>
        {resolveDialog}
      </>
    );
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Error Details</DialogTitle>
            <DialogDescription>
              View error information and resolution options
            </DialogDescription>
          </DialogHeader>
          {content}
          {footer && <DialogFooter>{footer}</DialogFooter>}
        </DialogContent>
      </Dialog>
      {resolveDialog}
    </>
  );
}
