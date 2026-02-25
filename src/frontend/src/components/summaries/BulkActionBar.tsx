/**
 * Bulk Action Bar Component (ADR-018)
 *
 * Provides multi-select and bulk operations for stored summaries.
 * Includes select all (page and filters), bulk delete, and bulk regenerate with confirmation dialogs.
 *
 * ADR-018 Enhancement: "Select all X matching filters" functionality for operations across all pages.
 */

import { useState } from "react";
import { Trash2, RefreshCw, X, CheckSquare, Square, CheckCheck } from "lucide-react";
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
import { useBulkDeleteSummaries, useBulkRegenerateSummaries, type BulkFilters } from "@/hooks/useStoredSummaries";

interface BulkActionBarProps {
  guildId: string;
  selectedIds: Set<string>;
  onSelectAll: () => void;
  onClearSelection: () => void;
  totalFilteredCount: number;
  allSelected: boolean;  // All on current page selected
  pageSize: number;
  currentFilters?: BulkFilters;  // Current filter state for "select all matching"
}

export function BulkActionBar({
  guildId,
  selectedIds,
  onSelectAll,
  onClearSelection,
  totalFilteredCount,
  allSelected,
  pageSize,
  currentFilters,
}: BulkActionBarProps) {
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [regenerateConfirmOpen, setRegenerateConfirmOpen] = useState(false);
  const [selectAllMatching, setSelectAllMatching] = useState(false);  // "Select all X matching filters" mode

  const { toast } = useToast();
  const bulkDeleteMutation = useBulkDeleteSummaries(guildId);
  const bulkRegenerateMutation = useBulkRegenerateSummaries(guildId);

  const selectedCount = selectAllMatching ? totalFilteredCount : selectedIds.size;
  const hasMoreThanOnePage = totalFilteredCount > pageSize;
  const showSelectAllMatchingBanner = allSelected && hasMoreThanOnePage && !selectAllMatching;

  const handleSelectAllMatching = () => {
    setSelectAllMatching(true);
  };

  const handleClearSelection = () => {
    setSelectAllMatching(false);
    onClearSelection();
  };

  const handleBulkDelete = async () => {
    try {
      // Use filters if "select all matching" is active, otherwise use IDs
      const request = selectAllMatching && currentFilters
        ? { filters: currentFilters }
        : { summary_ids: Array.from(selectedIds) };

      const result = await bulkDeleteMutation.mutateAsync(request);
      setDeleteConfirmOpen(false);
      handleClearSelection();
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
      // Use filters if "select all matching" is active, otherwise use IDs
      const request = selectAllMatching && currentFilters
        ? { filters: currentFilters }
        : { summary_ids: Array.from(selectedIds) };

      const result = await bulkRegenerateMutation.mutateAsync(request);
      setRegenerateConfirmOpen(false);
      handleClearSelection();
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

  if (selectedIds.size === 0 && !selectAllMatching) {
    return null;
  }

  return (
    <>
      <div className="space-y-2">
        {/* Main action bar */}
        <div className="flex items-center justify-between gap-4 p-3 bg-muted/50 rounded-lg border">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={allSelected ? handleClearSelection : onSelectAll}
              className="h-8"
            >
              {allSelected || selectAllMatching ? (
                <CheckSquare className="mr-2 h-4 w-4" />
              ) : (
                <Square className="mr-2 h-4 w-4" />
              )}
              {allSelected || selectAllMatching ? "Deselect All" : "Select All"}
            </Button>
            <Badge variant={selectAllMatching ? "default" : "secondary"} className="px-2 py-1">
              {selectAllMatching ? (
                <><CheckCheck className="mr-1 h-3 w-3 inline" />{totalFilteredCount} selected (all matching)</>
              ) : (
                <>{selectedIds.size} selected{totalFilteredCount > 0 && ` of ${totalFilteredCount}`}</>
              )}
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
              onClick={handleClearSelection}
              className="h-8 w-8 p-0"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* "Select all matching" banner - shown when entire page is selected and more items exist */}
        {showSelectAllMatchingBanner && (
          <div className="flex items-center justify-center gap-2 p-2 bg-primary/10 rounded-lg border border-primary/20 text-sm">
            <span className="text-muted-foreground">
              All {pageSize} items on this page selected.
            </span>
            <Button
              variant="link"
              size="sm"
              onClick={handleSelectAllMatching}
              className="h-auto p-0 text-primary font-medium"
            >
              Select all {totalFilteredCount} matching items
            </Button>
          </div>
        )}
      </div>

      {/* Delete Confirmation */}
      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selectedCount} Summaries?</AlertDialogTitle>
            <AlertDialogDescription>
              {selectAllMatching ? (
                <>
                  This will permanently delete <strong>all {selectedCount} summaries</strong> matching your current filters.
                  This action cannot be undone.
                </>
              ) : (
                <>
                  This will permanently delete {selectedCount} stored {selectedCount === 1 ? "summary" : "summaries"}.
                  This action cannot be undone.
                </>
              )}
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
              {selectAllMatching ? (
                <>
                  This will queue <strong>all {selectedCount} summaries</strong> matching your current filters for regeneration with grounding.
                  Summaries that already have grounding or cannot be regenerated will be skipped.
                  This may take some time to complete.
                </>
              ) : (
                <>
                  This will queue {selectedCount} {selectedCount === 1 ? "summary" : "summaries"} for regeneration with grounding.
                  Summaries that already have grounding or cannot be regenerated will be skipped.
                  This may take some time to complete.
                </>
              )}
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
