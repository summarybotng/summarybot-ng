/**
 * Run History Drawer Component (ADR-009)
 *
 * Shows execution history for a schedule with navigation to generated summaries.
 */

import { formatDistanceToNow } from "date-fns";
import { useNavigate, useParams } from "react-router-dom";
import { parseAsUTC } from "@/contexts/TimezoneContext";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  FileText,
  AlertTriangle,
  History,
} from "lucide-react";
import { useExecutionHistory } from "@/hooks/useSchedules";
import type { Schedule, ExecutionHistoryItem } from "@/types";

interface RunHistoryDrawerProps {
  schedule: Schedule | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function getStatusIcon(status: ExecutionHistoryItem["status"]) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-red-500" />;
    case "running":
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    case "cancelled":
      return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

function getStatusBadge(status: ExecutionHistoryItem["status"]) {
  switch (status) {
    case "completed":
      return <Badge variant="default" className="bg-green-500">Completed</Badge>;
    case "failed":
      return <Badge variant="destructive">Failed</Badge>;
    case "running":
      return <Badge variant="default" className="bg-blue-500">Running</Badge>;
    case "cancelled":
      return <Badge variant="secondary">Cancelled</Badge>;
    default:
      return <Badge variant="outline">Pending</Badge>;
  }
}

export function RunHistoryDrawer({
  schedule,
  open,
  onOpenChange,
}: RunHistoryDrawerProps) {
  const { id: guildId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: executions, isLoading } = useExecutionHistory(
    guildId || "",
    schedule?.id || null
  );

  const handleViewSummary = (summaryId: string) => {
    // Navigate to summaries page with this summary selected
    navigate(`/guilds/${guildId}/summaries?highlight=${summaryId}`);
    onOpenChange(false);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <History className="h-5 w-5" />
            Run History
          </SheetTitle>
          <SheetDescription>
            {schedule?.name} - Recent executions
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-8rem)] mt-6 pr-4">
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg border">
                  <Skeleton className="h-8 w-8 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-3 w-32" />
                  </div>
                </div>
              ))}
            </div>
          ) : !executions?.length ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <History className="h-12 w-12 text-muted-foreground/30 mb-4" />
              <h3 className="font-medium mb-1">No executions yet</h3>
              <p className="text-sm text-muted-foreground">
                This schedule hasn't run yet. Use the play button to run it now.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {executions.map((execution) => (
                <div
                  key={execution.execution_id}
                  className="flex items-start gap-3 p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
                >
                  <div className="mt-0.5">
                    {getStatusIcon(execution.status)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {getStatusBadge(execution.status)}
                      <span className="text-xs text-muted-foreground">
                        {formatDistanceToNow(parseAsUTC(execution.started_at), {
                          addSuffix: true,
                        })}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Started: {new Date(execution.started_at).toLocaleString()}
                    </p>
                    {execution.completed_at && (
                      <p className="text-xs text-muted-foreground">
                        Duration:{" "}
                        {Math.round(
                          (new Date(execution.completed_at).getTime() -
                            new Date(execution.started_at).getTime()) /
                            1000
                        )}
                        s
                      </p>
                    )}
                    {execution.error && (
                      <p className="text-xs text-red-500 mt-1 line-clamp-2">
                        {execution.error}
                      </p>
                    )}
                  </div>
                  {execution.summary_id && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleViewSummary(execution.summary_id!)}
                      className="shrink-0"
                    >
                      <FileText className="h-4 w-4 mr-1" />
                      View
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
