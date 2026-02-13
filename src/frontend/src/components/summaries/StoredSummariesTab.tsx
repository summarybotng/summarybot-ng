/**
 * Stored Summaries Tab Component (ADR-005)
 *
 * Displays stored summaries from dashboard delivery destination
 */

import { useState } from "react";
import { motion } from "framer-motion";
import { useStoredSummaries, useUpdateStoredSummary, useDeleteStoredSummary, usePushToChannel } from "@/hooks/useStoredSummaries";
import { useGuild } from "@/hooks/useGuilds";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/hooks/use-toast";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import {
  Archive,
  FileText,
  MessageSquare,
  Users,
  Send,
  Calendar,
  Pin,
  Clock,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { StoredSummaryCard } from "./StoredSummaryCard";
import { PushToChannelModal } from "./PushToChannelModal";
import type { StoredSummary, StoredSummaryDetail } from "@/types";

interface StoredSummariesTabProps {
  guildId: string;
}

export function StoredSummariesTab({ guildId }: StoredSummariesTabProps) {
  const [page, setPage] = useState(1);
  const [showArchived, setShowArchived] = useState(false);
  const [selectedSummary, setSelectedSummary] = useState<string | null>(null);
  const [pushModalSummary, setPushModalSummary] = useState<StoredSummary | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const { toast } = useToast();
  const { data: guild } = useGuild(guildId);
  const { data, isLoading, isError, refetch } = useStoredSummaries(guildId, {
    page,
    limit: 20,
    archived: showArchived,
  });

  const updateMutation = useUpdateStoredSummary(guildId);
  const deleteMutation = useDeleteStoredSummary(guildId);
  const pushMutation = usePushToChannel(guildId);

  const handlePin = async (summary: StoredSummary) => {
    try {
      await updateMutation.mutateAsync({
        summaryId: summary.id,
        data: { is_pinned: !summary.is_pinned },
      });
      toast({
        title: summary.is_pinned ? "Unpinned" : "Pinned",
        description: `Summary ${summary.is_pinned ? "unpinned" : "pinned"} successfully`,
      });
    } catch {
      toast({
        title: "Error",
        description: "Failed to update summary",
        variant: "destructive",
      });
    }
  };

  const handleArchive = async (summary: StoredSummary) => {
    try {
      await updateMutation.mutateAsync({
        summaryId: summary.id,
        data: { is_archived: !summary.is_archived },
      });
      toast({
        title: summary.is_archived ? "Unarchived" : "Archived",
        description: `Summary ${summary.is_archived ? "restored" : "archived"} successfully`,
      });
    } catch {
      toast({
        title: "Error",
        description: "Failed to update summary",
        variant: "destructive",
      });
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirmId) return;
    try {
      await deleteMutation.mutateAsync(deleteConfirmId);
      setDeleteConfirmId(null);
      toast({
        title: "Deleted",
        description: "Summary deleted successfully",
      });
    } catch {
      toast({
        title: "Error",
        description: "Failed to delete summary",
        variant: "destructive",
      });
    }
  };

  const handlePush = async (request: Parameters<typeof pushMutation.mutateAsync>[0]["request"]) => {
    if (!pushModalSummary) return;
    try {
      const result = await pushMutation.mutateAsync({
        summaryId: pushModalSummary.id,
        request,
      });
      setPushModalSummary(null);
      toast({
        title: result.success ? "Pushed successfully" : "Partially pushed",
        description: `Sent to ${result.successful_channels}/${result.total_channels} channels`,
        variant: result.success ? "default" : "destructive",
      });
    } catch {
      toast({
        title: "Error",
        description: "Failed to push summary",
        variant: "destructive",
      });
    }
  };

  if (isError) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="flex items-center justify-between p-4">
            <div className="flex items-center gap-3">
              <AlertCircle className="h-5 w-5 text-destructive" />
              <div>
                <p className="font-medium text-destructive">Failed to load stored summaries</p>
                <p className="text-sm text-muted-foreground">Please try again</p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Retry
            </Button>
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  if (isLoading) {
    return <StoredSummariesSkeleton />;
  }

  const summaries = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / 20);

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="flex items-center space-x-2">
          <Checkbox
            id="show-archived"
            checked={showArchived}
            onCheckedChange={(checked) => setShowArchived(checked as boolean)}
          />
          <label htmlFor="show-archived" className="text-sm cursor-pointer">
            Show archived
          </label>
        </div>
        <span className="text-sm text-muted-foreground">
          {total} stored {total === 1 ? "summary" : "summaries"}
        </span>
      </div>

      {/* Empty State */}
      {summaries.length === 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center justify-center py-20"
        >
          <Archive className="mb-4 h-16 w-16 text-muted-foreground/30" />
          <h2 className="mb-2 text-xl font-semibold">No stored summaries</h2>
          <p className="text-center text-muted-foreground">
            {showArchived
              ? "No archived summaries found"
              : "Create a schedule with Dashboard destination to store summaries here"}
          </p>
        </motion.div>
      )}

      {/* Summary List */}
      <div className="grid gap-4">
        {summaries.map((summary, index) => (
          <StoredSummaryCard
            key={summary.id}
            summary={summary}
            index={index}
            onView={() => setSelectedSummary(summary.id)}
            onPush={() => setPushModalSummary(summary)}
            onPin={() => handlePin(summary)}
            onArchive={() => handleArchive(summary)}
            onDelete={() => setDeleteConfirmId(summary.id)}
          />
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            Next
          </Button>
        </div>
      )}

      {/* Detail Sheet */}
      <StoredSummaryDetailSheet
        guildId={guildId}
        summaryId={selectedSummary}
        open={!!selectedSummary}
        onOpenChange={(open) => !open && setSelectedSummary(null)}
        onPush={(summaryId) => {
          const summary = summaries.find((s) => s.id === summaryId);
          if (summary) {
            setPushModalSummary(summary);
          }
        }}
      />

      {/* Push Modal */}
      {pushModalSummary && guild && (
        <PushToChannelModal
          open={!!pushModalSummary}
          onOpenChange={(open) => !open && setPushModalSummary(null)}
          channels={guild.channels}
          summaryTitle={pushModalSummary.title}
          isPending={pushMutation.isPending}
          onSubmit={handlePush}
        />
      )}

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteConfirmId} onOpenChange={(open) => !open && setDeleteConfirmId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Summary?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the stored summary. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// Detail Sheet Component
function StoredSummaryDetailSheet({
  guildId,
  summaryId,
  open,
  onOpenChange,
  onPush,
}: {
  guildId: string;
  summaryId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPush: (summaryId: string) => void;
}) {
  const { data: summary, isLoading } = useStoredSummaries(guildId, {});
  // For a real implementation, we'd use useStoredSummary(guildId, summaryId)
  // For now, we'll show basic info

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
          </div>
        ) : summaryId ? (
          <>
            <SheetHeader>
              <SheetTitle>Stored Summary</SheetTitle>
              <SheetDescription>
                View and manage this stored summary
              </SheetDescription>
            </SheetHeader>

            <div className="mt-6 space-y-4">
              <Button onClick={() => onPush(summaryId)} className="w-full">
                <Send className="mr-2 h-4 w-4" />
                Push to Channel
              </Button>

              <p className="text-sm text-muted-foreground text-center">
                Full summary details will be displayed here
              </p>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

// Skeleton
function StoredSummariesSkeleton() {
  return (
    <div className="grid gap-4">
      {[1, 2, 3].map((i) => (
        <Card key={i} className="border-border/50">
          <CardContent className="p-5">
            <div className="mb-3 flex justify-between">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-20" />
            </div>
            <div className="mb-3 flex gap-2">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-5 w-16" />
            </div>
            <div className="flex gap-4">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-4 w-24" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
