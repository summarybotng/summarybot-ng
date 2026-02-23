/**
 * Bulk Action Bar Component (ADR-018)
 *
 * Provides multi-select and bulk operations for stored summaries.
 * Includes select all, bulk delete, and bulk regenerate with confirmation dialogs.
 */

import { useState } from "react";
import { Trash2, RefreshCw, X, CheckSquare, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { useToast } from "@/hooks/use-toast";
import { useBulkDeleteSummaries, useBulkRegenerateSummaries } from "@/hooks/useStoredSummaries";

interface BulkActionBarProps {
  guildId: string;
  selectedIds: Set<string>;
  onSelectAll: () => void;
  onClearSelection: () => void;
  totalFilteredCount: number;
  allSelected: boolean;
}

export function BulkActionBar({
  guildId,
  selectedIds,
  onSelectAll,
  onClearSelection,
  totalFilteredCount,
  allSelected,
}: BulkActionBarProps) {
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [regenerateConfirmOpen, setRegenerateConfirmOpen] = useState(false);

  const { toast } = useToast();
  const bulkDeleteMutation = useBulkDeleteSummaries(guildId);
  const bulkRegenerateMutation = useBulkRegenerateSummaries(guildId);

  const selectedCount = selectedIds.size;

  const handleBulkDelete = async () => {
    try {
      const result = await bulkDeleteMutation.mutateAsync(Array.from(selectedIds));
      setDeleteConfirmOpen(false);
      onClearSelection();
      toast({
        title: "Bulk Delete Complete",
        description: `Deleted ${result.deleted_count} summaries${result.failed_ids.length > 0 ? `, ${result.failed_ids.length} failed` : ""}`,
        variant: result.failed_ids.length > 0 ? "destructive" : "default",
      });
    } catch (error) {
      toast({
        title: "Bulk Delete Failed",
        description: "An error occurred while deleting summaries",
        variant: "destructive",
      });
    }
  };

  const handleBulkRegenerate = async () => {
    try {
      const result = await bulkRegenerateMutation.mutateAsync(Array.from(selectedIds));
      setRegenerateConfirmOpen(false);
      onClearSelection();
      toast({
        title: "Bulk Regeneration Started",
        description: `Queued ${result.queued_count} summaries for regeneration${result.skipped_count > 0 ? `, ${result.skipped_count} skipped` : ""}`,
      });
    } catch (error) {
      toast({
        title: "Bulk Regeneration Failed",
        description: "An error occurred while starting regeneration",
        variant: "destructive",
      });
    }
  };

  if (selectedCount === 0) {
    return null;
  }

  return (
    <>
      <div className="flex items-center justify-between gap-4 p-3 bg-muted/50 rounded-lg border">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={allSelected ? onClearSelection : onSelectAll}
            className="h-8"
          >
            {allSelected ? (
              <CheckSquare className="mr-2 h-4 w-4" />
            ) : (
              <Square className="mr-2 h-4 w-4" />
            )}
            {allSelected ? "Deselect All" : "Select All"}
          </Button>
          <Badge variant="secondary" className="px-2 py-1">
            {selectedCount} selected
            {totalFilteredCount > 0 && ` of ${totalFilteredCount}`}
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRegenerateConfirmOpen(true)}
            disabled={bulkRegenerateMutation.isPending}
            className="h-8"
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${bulkRegenerateMutation.isPending ? "animate-spin" : ""}`} />
            Regenerate ({selectedCount})
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setDeleteConfirmOpen(true)}
            disabled={bulkDeleteMutation.isPending}
            className="h-8"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete ({selectedCount})
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearSelection}
            className="h-8 w-8 p-0"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Delete Confirmation */}
      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selectedCount} Summaries?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete {selectedCount} stored {selectedCount === 1 ? "summary" : "summaries"}.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleBulkDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {bulkDeleteMutation.isPending ? "Deleting..." : `Delete ${selectedCount}`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Regenerate Confirmation */}
      <AlertDialog open={regenerateConfirmOpen} onOpenChange={setRegenerateConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Regenerate {selectedCount} Summaries?</AlertDialogTitle>
            <AlertDialogDescription>
              This will queue {selectedCount} {selectedCount === 1 ? "summary" : "summaries"} for regeneration with grounding.
              Summaries that already have grounding or cannot be regenerated will be skipped.
              This may take some time to complete.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleBulkRegenerate}>
              {bulkRegenerateMutation.isPending ? "Starting..." : `Regenerate ${selectedCount}`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
