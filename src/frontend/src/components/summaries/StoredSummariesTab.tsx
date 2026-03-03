/**
 * Stored Summaries Tab Component (ADR-005, ADR-008, ADR-017)
 *
 * Displays stored summaries from dashboard delivery destination.
 * ADR-008: Extended to show unified view of both real-time and archive summaries.
 * ADR-017: Enhanced with calendar view, filtering, sorting, and integrity indicators.
 */

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import { useStoredSummaries, useStoredSummary, useUpdateStoredSummary, useDeleteStoredSummary, usePushToChannel, useSendToEmail, useRegenerateSummary, type SummarySourceType, type RegenerateOptions } from "@/hooks/useStoredSummaries";
import { useGuild } from "@/hooks/useGuilds";
import { useTimezone, parseAsUTC } from "@/contexts/TimezoneContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  Link,
  History,
  GitBranch,
  ExternalLink,
  Sparkles,
  Settings2,
  LayoutList,
  CalendarDays,
  Copy,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { StoredSummaryCard } from "./StoredSummaryCard";
import { PushToChannelModal } from "./PushToChannelModal";
import { SendToEmailModal, type SendToEmailRequest } from "./SendToEmailModal";
import { SummaryFilters, type FilterState } from "./SummaryFilters";
import { SummaryCalendar } from "./SummaryCalendar";
import { BulkActionBar } from "./BulkActionBar";
import type { StoredSummary, StoredSummaryDetail } from "@/types";

// Helper to group summaries by recency
function groupSummariesByRecency(summaries: StoredSummary[]): {
  today: StoredSummary[];
  lastThreeDays: StoredSummary[];
  thisWeek: StoredSummary[];
  older: StoredSummary[];
} {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const threeDaysAgo = new Date(today.getTime() - 3 * 24 * 60 * 60 * 1000);
  const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

  const groups = {
    today: [] as StoredSummary[],
    lastThreeDays: [] as StoredSummary[],
    thisWeek: [] as StoredSummary[],
    older: [] as StoredSummary[],
  };

  for (const summary of summaries) {
    const createdAt = parseAsUTC(summary.created_at);
    if (createdAt >= today) {
      groups.today.push(summary);
    } else if (createdAt >= threeDaysAgo) {
      groups.lastThreeDays.push(summary);
    } else if (createdAt >= weekAgo) {
      groups.thisWeek.push(summary);
    } else {
      groups.older.push(summary);
    }
  }

  return groups;
}

interface StoredSummariesTabProps {
  guildId: string;
  initialSource?: SummarySourceType;  // ADR-009: For deep linking from Archive page
}

export function StoredSummariesTab({ guildId, initialSource }: StoredSummariesTabProps) {
  const [page, setPage] = useState(1);
  const [viewMode, setViewMode] = useState<"list" | "calendar">("list");  // ADR-017
  const [selectedSummary, setSelectedSummary] = useState<string | null>(null);
  const [pushModalSummary, setPushModalSummary] = useState<StoredSummary | null>(null);
  const [emailModalSummary, setEmailModalSummary] = useState<StoredSummary | null>(null);  // ADR-030
  const [emailError, setEmailError] = useState<string | null>(null);  // ADR-030
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  // ADR-018: Bulk selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isRefreshing, setIsRefreshing] = useState(false);

  // ADR-017: Unified filter state
  const [filters, setFilters] = useState<FilterState>({
    source: initialSource || "all",
    archived: false,
    channelMode: "all",
    sortBy: "created_at",
    sortOrder: "desc",
  });

  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data: guild } = useGuild(guildId);
  const { data, isLoading, isError, refetch } = useStoredSummaries(guildId, {
    page,
    limit: 20,
    archived: filters.archived,
    source: filters.source,
    createdAfter: filters.createdAfter,
    createdBefore: filters.createdBefore,
    archivePeriod: filters.archivePeriod,
    channelMode: filters.channelMode,
    hasGrounding: filters.hasGrounding,
    sortBy: filters.sortBy,
    sortOrder: filters.sortOrder,
    // ADR-018: Content filters
    hasKeyPoints: filters.hasKeyPoints,
    hasActionItems: filters.hasActionItems,
    hasParticipants: filters.hasParticipants,
    minMessageCount: filters.minMessageCount,
    maxMessageCount: filters.maxMessageCount,
    // ADR-021: Content count filters
    minKeyPoints: filters.minKeyPoints,
    maxKeyPoints: filters.maxKeyPoints,
    minActionItems: filters.minActionItems,
    maxActionItems: filters.maxActionItems,
    minParticipants: filters.minParticipants,
    maxParticipants: filters.maxParticipants,
    // ADR-026: Platform filter
    platform: filters.platform,
  });

  const updateMutation = useUpdateStoredSummary(guildId);
  const deleteMutation = useDeleteStoredSummary(guildId);
  const pushMutation = usePushToChannel(guildId);
  const emailMutation = useSendToEmail(guildId);  // ADR-030
  const regenerateMutation = useRegenerateSummary(guildId);

  // Refresh both list and calendar views
  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      // Use refetchQueries with type: 'all' to refetch both active AND inactive queries
      // This ensures calendar data is refreshed even when calendar view isn't mounted
      await Promise.all([
        queryClient.refetchQueries({
          queryKey: ["stored-summaries", guildId],
          type: 'all',
        }),
        queryClient.refetchQueries({
          queryKey: ["summary-calendar", guildId],
          type: 'all',
        }),
      ]);
      toast({
        title: "Refreshed",
        description: "Summary list and calendar synced",
      });
    } catch {
      toast({
        title: "Refresh failed",
        description: "Could not refresh data",
        variant: "destructive",
      });
    } finally {
      setIsRefreshing(false);
    }
  };

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

  // ADR-004: Regenerate summary with grounding (with optional custom options)
  const handleRegenerate = async (summaryId: string, options?: RegenerateOptions) => {
    try {
      await regenerateMutation.mutateAsync({ summaryId, options });
      const optionsDesc = options
        ? ` with ${[
            options.model && `model: ${options.model}`,
            options.summary_length && `length: ${options.summary_length}`,
            options.perspective && `perspective: ${options.perspective}`,
          ].filter(Boolean).join(", ")}`
        : "";
      toast({
        title: "Regenerating",
        description: `Summary is being regenerated${optionsDesc}. This may take a moment.`,
      });
    } catch (error: unknown) {
      // Extract error message from API response
      const errorMessage = error && typeof error === 'object' && 'detail' in error
        ? (error as { detail?: { message?: string } | string }).detail
        : null;
      const message = typeof errorMessage === 'string'
        ? errorMessage
        : errorMessage?.message || "Failed to start regeneration";
      toast({
        title: "Error",
        description: message,
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

  // ADR-030: Email handling
  const handleEmail = async (request: SendToEmailRequest) => {
    if (!emailModalSummary) return;
    setEmailError(null);
    try {
      const result = await emailMutation.mutateAsync({
        summaryId: emailModalSummary.id,
        request,
      });
      setEmailModalSummary(null);
      toast({
        title: result.success ? "Email sent" : "Partially sent",
        description: `Sent to ${result.successful_recipients}/${result.total_recipients} recipients`,
        variant: result.success ? "default" : "destructive",
      });
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to send email";
      // Check for specific error codes
      if (errorMessage.includes("EMAIL_NOT_CONFIGURED")) {
        setEmailError("Email is not configured on the server. Contact your administrator.");
      } else {
        setEmailError(errorMessage);
      }
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

  // ADR-017: Handle date selection from calendar
  const handleDateSelect = (date: string) => {
    setFilters(prev => ({
      ...prev,
      archivePeriod: date,
      createdAfter: undefined,
      createdBefore: undefined,
    }));
    setViewMode("list");
  };

  // ADR-018: Selection handlers
  const handleToggleSelect = (summaryId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(summaryId)) {
        next.delete(summaryId);
      } else {
        next.add(summaryId);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    setSelectedIds(new Set(summaries.map(s => s.id)));
  };

  const handleClearSelection = () => {
    setSelectedIds(new Set());
  };

  const allSelected = summaries.length > 0 && summaries.every(s => selectedIds.has(s.id));

  return (
    <div className="space-y-4">
      {/* ADR-017: View mode toggle and filters */}
      <div className="flex items-center justify-between gap-4">
        <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as "list" | "calendar")} className="w-auto">
          <TabsList className="h-8">
            <TabsTrigger value="list" className="h-7 px-3">
              <LayoutList className="h-4 w-4 mr-1" />
              List
            </TabsTrigger>
            <TabsTrigger value="calendar" className="h-7 px-3">
              <CalendarDays className="h-4 w-4 mr-1" />
              Calendar
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRefresh}
          disabled={isRefreshing}
          title="Refresh list and calendar"
        >
          <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* ADR-017: Enhanced filters */}
      {viewMode === "list" && (
        <SummaryFilters
          filters={filters}
          onFiltersChange={(newFilters) => {
            setFilters(newFilters);
            setPage(1);  // Reset to first page when filters change
          }}
          totalCount={total}
        />
      )}

      {/* ADR-017: Calendar View */}
      {viewMode === "calendar" && (
        <SummaryCalendar
          guildId={guildId}
          onDateSelect={handleDateSelect}
          selectedDate={filters.archivePeriod}
        />
      )}

      {/* ADR-018: Bulk Action Bar */}
      {viewMode === "list" && selectedIds.size > 0 && (
        <BulkActionBar
          guildId={guildId}
          selectedIds={selectedIds}
          onSelectAll={handleSelectAll}
          onClearSelection={handleClearSelection}
          totalFilteredCount={total}
          allSelected={allSelected}
          pageSize={20}
          currentFilters={{
            source: filters.source !== "all" ? filters.source : undefined,
            archived: filters.archived,
            created_after: filters.createdAfter,
            created_before: filters.createdBefore,
            archive_period: filters.archivePeriod,
            channel_mode: filters.channelMode !== "all" ? filters.channelMode : undefined,
            has_grounding: filters.hasGrounding,
            has_key_points: filters.hasKeyPoints,
            has_action_items: filters.hasActionItems,
            has_participants: filters.hasParticipants,
            min_message_count: filters.minMessageCount,
            max_message_count: filters.maxMessageCount,
          }}
        />
      )}

      {/* List View Content */}
      {viewMode === "list" && (
        <>
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
                {filters.archived
                  ? "No archived summaries found"
                  : "Create a schedule with Dashboard destination to store summaries here"}
              </p>
            </motion.div>
          )}

          {/* ADR-018: Selection header - always visible when summaries exist */}
          {summaries.length > 0 && (
            <div className="flex items-center gap-3 py-2 px-1 border-b">
              <Checkbox
                checked={allSelected && summaries.length > 0}
                onCheckedChange={(checked) => {
                  if (checked) {
                    handleSelectAll();
                  } else {
                    handleClearSelection();
                  }
                }}
                aria-label="Select all on page"
              />
              <span className="text-sm text-muted-foreground">
                {selectedIds.size === 0 ? (
                  `${total} summaries`
                ) : allSelected ? (
                  <span className="text-foreground font-medium">All {summaries.length} on this page selected</span>
                ) : (
                  <span className="text-foreground">{selectedIds.size} selected</span>
                )}
              </span>
              {selectedIds.size > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleClearSelection}
                  className="h-6 px-2 text-xs"
                >
                  Clear
                </Button>
              )}
            </div>
          )}

          {/* Summary List - Grouped by Recency */}
          {(() => {
            const groups = groupSummariesByRecency(summaries);
            let globalIndex = 0;

            const renderGroup = (title: string, items: StoredSummary[], icon: React.ReactNode) => {
              if (items.length === 0) return null;
              const startIndex = globalIndex;
              globalIndex += items.length;
              return (
                <div key={title} className="space-y-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                    {icon}
                    <span>{title}</span>
                    <span className="text-xs">({items.length})</span>
                  </div>
                  <div className="grid gap-3">
                    {items.map((summary, idx) => (
                      <StoredSummaryCard
                        key={summary.id}
                        summary={summary}
                        index={startIndex + idx}
                        onView={() => setSelectedSummary(summary.id)}
                        onPush={() => setPushModalSummary(summary)}
                        onEmail={() => setEmailModalSummary(summary)}
                        onPin={() => handlePin(summary)}
                        onArchive={() => handleArchive(summary)}
                        onDelete={() => setDeleteConfirmId(summary.id)}
                        isSelected={selectedIds.has(summary.id)}
                        onToggleSelect={() => handleToggleSelect(summary.id)}
                      />
                    ))}
                  </div>
                </div>
              );
            };

            return (
              <div className="space-y-6">
                {renderGroup("Today", groups.today, <Clock className="h-4 w-4" />)}
                {renderGroup("Last 3 Days", groups.lastThreeDays, <Calendar className="h-4 w-4" />)}
                {renderGroup("This Week", groups.thisWeek, <Calendar className="h-4 w-4" />)}
                {renderGroup("Older", groups.older, <History className="h-4 w-4" />)}
              </div>
            );
          })()}

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
        </>
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
        onRegenerate={handleRegenerate}
        isRegenerating={regenerateMutation.isPending}
        onNavigate={(newSummaryId) => setSelectedSummary(newSummaryId)}
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
          guildId={guildId}
        />
      )}

      {/* ADR-030: Email Modal */}
      {emailModalSummary && (
        <SendToEmailModal
          open={!!emailModalSummary}
          onOpenChange={(open) => {
            if (!open) {
              setEmailModalSummary(null);
              setEmailError(null);
            }
          }}
          summaryTitle={emailModalSummary.title}
          isPending={emailMutation.isPending}
          onSubmit={handleEmail}
          error={emailError}
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

// Copy button component
function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-7 px-2 text-xs"
      onClick={handleCopy}
      title={`Copy ${label}`}
    >
      {copied ? (
        <>
          <Check className="h-3 w-3 mr-1" />
          Copied
        </>
      ) : (
        <>
          <Copy className="h-3 w-3 mr-1" />
          Copy
        </>
      )}
    </Button>
  );
}

// Available models for regeneration
const AVAILABLE_MODELS = [
  { value: "claude-sonnet-4-20250514", label: "Claude Sonnet 4" },
  { value: "claude-3-5-sonnet-20241022", label: "Claude 3.5 Sonnet" },
  { value: "claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku" },
];

const SUMMARY_LENGTHS = [
  { value: "brief", label: "Brief" },
  { value: "detailed", label: "Detailed" },
  { value: "comprehensive", label: "Comprehensive" },
];

const PERSPECTIVES = [
  { value: "general", label: "General" },
  { value: "developer", label: "Developer" },
  { value: "marketing", label: "Marketing" },
  { value: "executive", label: "Executive" },
  { value: "support", label: "Support" },
];

// Detail Sheet Component
function StoredSummaryDetailSheet({
  guildId,
  summaryId,
  open,
  onOpenChange,
  onPush,
  onRegenerate,
  isRegenerating,
  onNavigate,
}: {
  guildId: string;
  summaryId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPush: (summaryId: string) => void;
  onRegenerate: (summaryId: string, options?: RegenerateOptions) => void;
  isRegenerating: boolean;
  onNavigate?: (summaryId: string) => void;
}) {
  const { data: summary, isLoading } = useStoredSummary(guildId, summaryId || "");
  const { formatDateTime, formatTime } = useTimezone();
  const [regenerateDialogOpen, setRegenerateDialogOpen] = useState(false);
  const [regenerateOptions, setRegenerateOptions] = useState<RegenerateOptions>({});

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-[50vw] lg:max-w-[70vw]">
        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : summary ? (
          <>
            <SheetHeader>
              <div className="flex items-center justify-between gap-2">
                <SheetTitle className="flex-1">{summary.title}</SheetTitle>
                {/* ADR-020: Navigation buttons */}
                {summary.navigation && onNavigate && (
                  <div className="flex items-center gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => summary.navigation?.previous_id && onNavigate(summary.navigation.previous_id)}
                      disabled={!summary.navigation.previous_id}
                      title={summary.navigation.previous_date ? `Previous: ${summary.navigation.previous_date}` : "No previous summary"}
                    >
                      <ChevronLeft className="h-4 w-4" />
                      <span className="sr-only">Previous</span>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => summary.navigation?.next_id && onNavigate(summary.navigation.next_id)}
                      disabled={!summary.navigation.next_id}
                      title={summary.navigation.next_date ? `Next: ${summary.navigation.next_date}` : "No next summary"}
                    >
                      <ChevronRight className="h-4 w-4" />
                      <span className="sr-only">Next</span>
                    </Button>
                  </div>
                )}
              </div>
              <SheetDescription className="space-y-1">
                <div>
                  {summary.start_time && summary.end_time
                    ? `${formatDateTime(summary.start_time)} - ${formatDateTime(summary.end_time)}`
                    : `Created ${formatDateTime(summary.created_at)}`}
                </div>
                <div className="font-mono text-xs">ID: {summary.id}</div>
              </SheetDescription>
            </SheetHeader>

            <div className="mt-6 space-y-6">
              {/* Stats */}
              <div className="flex flex-wrap gap-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <MessageSquare className="h-4 w-4" />
                  <span>{summary.message_count} messages</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Users className="h-4 w-4" />
                  <span>{summary.participants?.length || 0} participants</span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => onPush(summary.id)} className="w-full sm:w-auto">
                  <Send className="mr-2 h-4 w-4" />
                  Push to Channel
                </Button>
                {/* ADR-004: Regenerate button - now always available with options */}
                <Button
                  variant="outline"
                  onClick={() => setRegenerateDialogOpen(true)}
                  disabled={isRegenerating}
                  className="w-full sm:w-auto"
                >
                  <RefreshCw className={`mr-2 h-4 w-4 ${isRegenerating ? 'animate-spin' : ''}`} />
                  {isRegenerating ? 'Regenerating...' : 'Regenerate'}
                  <ChevronDown className="ml-1 h-3 w-3" />
                </Button>
              </div>

              {/* Regenerate Options Dialog */}
              <Dialog open={regenerateDialogOpen} onOpenChange={setRegenerateDialogOpen}>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Regenerate Summary</DialogTitle>
                    <DialogDescription>
                      Customize regeneration settings or use defaults to add grounding references.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="grid gap-4 py-4">
                    <div className="grid gap-2">
                      <Label>Model</Label>
                      <Select
                        value={regenerateOptions.model || ""}
                        onValueChange={(v) => setRegenerateOptions(prev => ({ ...prev, model: v || undefined }))}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Use original model" />
                        </SelectTrigger>
                        <SelectContent>
                          {AVAILABLE_MODELS.map(m => (
                            <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="grid gap-2">
                      <Label>Summary Length</Label>
                      <Select
                        value={regenerateOptions.summary_length || ""}
                        onValueChange={(v) => setRegenerateOptions(prev => ({ ...prev, summary_length: v || undefined }))}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Use original length" />
                        </SelectTrigger>
                        <SelectContent>
                          {SUMMARY_LENGTHS.map(l => (
                            <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="grid gap-2">
                      <Label>Perspective</Label>
                      <Select
                        value={regenerateOptions.perspective || ""}
                        onValueChange={(v) => setRegenerateOptions(prev => ({ ...prev, perspective: v || undefined }))}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Use original perspective" />
                        </SelectTrigger>
                        <SelectContent>
                          {PERSPECTIVES.map(p => (
                            <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setRegenerateDialogOpen(false)}>
                      Cancel
                    </Button>
                    <Button
                      onClick={() => {
                        const hasOptions = Object.values(regenerateOptions).some(v => v);
                        onRegenerate(summary.id, hasOptions ? regenerateOptions : undefined);
                        setRegenerateDialogOpen(false);
                        setRegenerateOptions({});
                      }}
                      disabled={isRegenerating}
                    >
                      <RefreshCw className={`mr-2 h-4 w-4 ${isRegenerating ? 'animate-spin' : ''}`} />
                      Regenerate
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

              {/* Summary Text */}
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-base">Summary</CardTitle>
                  <CopyButton text={summary.summary_text || ""} label="summary" />
                </CardHeader>
                <CardContent>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {summary.summary_text}
                  </p>
                </CardContent>
              </Card>

              {/* Key Points */}
              {summary.key_points && summary.key_points.length > 0 && (
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-base">Key Points</CardTitle>
                    <CopyButton
                      text={summary.key_points.map((p, i) => `${i + 1}. ${p}`).join("\n")}
                      label="key points"
                    />
                  </CardHeader>
                  <CardContent>
                    <ul className="list-inside list-disc space-y-2 text-sm">
                      {summary.key_points.map((point, i) => (
                        <li key={i}>{point}</li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              {/* Action Items */}
              {summary.action_items && summary.action_items.length > 0 && (
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-base">Action Items</CardTitle>
                    <CopyButton
                      text={summary.action_items.map((item, i) =>
                        `${i + 1}. [${item.priority.toUpperCase()}] ${item.text}${item.assignee ? ` (${item.assignee})` : ""}`
                      ).join("\n")}
                      label="action items"
                    />
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-3">
                      {summary.action_items.map((item, i) => (
                        <li key={i} className="flex items-start gap-3">
                          <Badge
                            variant={
                              item.priority === "high"
                                ? "destructive"
                                : item.priority === "medium"
                                ? "default"
                                : "secondary"
                            }
                            className="mt-0.5"
                          >
                            {item.priority}
                          </Badge>
                          <div className="flex-1">
                            <p className="text-sm">{item.text}</p>
                            {item.assignee && (
                              <p className="text-xs text-muted-foreground">
                                Assigned to: {item.assignee}
                              </p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              {/* References (ADR-004) */}
              {summary.references && summary.references.length > 0 && (
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Link className="h-4 w-4" />
                      References
                    </CardTitle>
                    <CopyButton
                      text={summary.references.map(ref =>
                        `[${ref.id}] ${ref.author} (${ref.timestamp}): ${ref.content}`
                      ).join("\n")}
                      label="references"
                    />
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-muted-foreground">
                            <th className="pb-2 pr-4 font-medium">#</th>
                            <th className="pb-2 pr-4 font-medium">Who</th>
                            <th className="pb-2 pr-4 font-medium">When</th>
                            <th className="pb-2 font-medium">Said</th>
                          </tr>
                        </thead>
                        <tbody>
                          {summary.references.map((ref) => (
                            <tr key={ref.id} className="border-b border-border/50 last:border-0">
                              <td className="py-2 pr-4 text-muted-foreground">[{ref.id}]</td>
                              <td className="py-2 pr-4 font-medium">{ref.author}</td>
                              <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">
                                {formatTime(ref.timestamp)}
                              </td>
                              <td className="py-2 text-muted-foreground">{ref.content}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* ADR-010: How This Summary Was Generated - ALL METADATA */}
              {summary.metadata && (
                <Card className="bg-muted/30">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Settings2 className="h-4 w-4" />
                      How This Summary Was Generated
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      {/* Core generation settings */}
                      {(summary.metadata.model_used || summary.metadata.model) && (
                        <div>
                          <span className="text-muted-foreground">Model:</span>{" "}
                          <span className="font-medium flex items-center gap-1 inline-flex">
                            <Sparkles className="h-3 w-3" />
                            {(summary.metadata.model_used || summary.metadata.model)?.replace("claude-", "").replace(/-/g, " ")}
                          </span>
                        </div>
                      )}
                      {summary.metadata.summary_length && (
                        <div>
                          <span className="text-muted-foreground">Length:</span>{" "}
                          <span className="font-medium capitalize">{summary.metadata.summary_length}</span>
                        </div>
                      )}
                      {summary.metadata.perspective && (
                        <div>
                          <span className="text-muted-foreground">Perspective:</span>{" "}
                          <span className="font-medium capitalize">{summary.metadata.perspective}</span>
                        </div>
                      )}
                      {typeof summary.metadata.tokens_used === "number" && (
                        <div>
                          <span className="text-muted-foreground">Tokens:</span>{" "}
                          <span className="font-medium">{summary.metadata.tokens_used.toLocaleString()}</span>
                        </div>
                      )}
                      {/* Extended metadata fields */}
                      {typeof summary.metadata.input_tokens === "number" && (
                        <div>
                          <span className="text-muted-foreground">Input Tokens:</span>{" "}
                          <span className="font-medium">{summary.metadata.input_tokens.toLocaleString()}</span>
                        </div>
                      )}
                      {typeof summary.metadata.output_tokens === "number" && (
                        <div>
                          <span className="text-muted-foreground">Output Tokens:</span>{" "}
                          <span className="font-medium">{summary.metadata.output_tokens.toLocaleString()}</span>
                        </div>
                      )}
                      {typeof summary.metadata.generation_time_ms === "number" && (
                        <div>
                          <span className="text-muted-foreground">Generation Time:</span>{" "}
                          <span className="font-medium">{(summary.metadata.generation_time_ms / 1000).toFixed(2)}s</span>
                        </div>
                      )}
                      {summary.metadata.summary_type && (
                        <div>
                          <span className="text-muted-foreground">Type:</span>{" "}
                          <span className="font-medium capitalize">{summary.metadata.summary_type}</span>
                        </div>
                      )}
                      {summary.metadata.grounded !== undefined && (
                        <div>
                          <span className="text-muted-foreground">Grounded:</span>{" "}
                          <span className="font-medium">{summary.metadata.grounded ? "Yes" : "No"}</span>
                        </div>
                      )}
                      {typeof summary.metadata.reference_count === "number" && (
                        <div>
                          <span className="text-muted-foreground">References:</span>{" "}
                          <span className="font-medium">{summary.metadata.reference_count}</span>
                        </div>
                      )}
                      {summary.metadata.channel_name && (
                        <div>
                          <span className="text-muted-foreground">Channel:</span>{" "}
                          <span className="font-medium">#{summary.metadata.channel_name}</span>
                        </div>
                      )}
                      {summary.metadata.guild_name && (
                        <div>
                          <span className="text-muted-foreground">Server:</span>{" "}
                          <span className="font-medium">{summary.metadata.guild_name}</span>
                        </div>
                      )}
                      {typeof summary.metadata.time_span_hours === "number" && (
                        <div>
                          <span className="text-muted-foreground">Time Span:</span>{" "}
                          <span className="font-medium">{summary.metadata.time_span_hours.toFixed(1)}h</span>
                        </div>
                      )}
                      {typeof summary.metadata.total_participants === "number" && (
                        <div>
                          <span className="text-muted-foreground">Participants:</span>{" "}
                          <span className="font-medium">{summary.metadata.total_participants}</span>
                        </div>
                      )}
                      {summary.metadata.api_version && (
                        <div>
                          <span className="text-muted-foreground">API Version:</span>{" "}
                          <span className="font-medium">{summary.metadata.api_version}</span>
                        </div>
                      )}
                      {summary.metadata.cache_status && (
                        <div>
                          <span className="text-muted-foreground">Cache:</span>{" "}
                          <span className="font-medium capitalize">{summary.metadata.cache_status}</span>
                        </div>
                      )}
                    </div>

                    {/* Show any additional unknown metadata fields */}
                    {(() => {
                      const knownKeys = new Set([
                        "model", "model_used", "summary_length", "perspective", "tokens_used",
                        "input_tokens", "output_tokens", "generation_time_ms", "summary_type",
                        "grounded", "reference_count", "channel_name", "guild_name",
                        "time_span_hours", "total_participants", "api_version", "cache_status",
                        "prompt_source", // handled separately
                      ]);
                      const extraFields = Object.entries(summary.metadata)
                        .filter(([key, value]) => !knownKeys.has(key) && value !== null && value !== undefined && key !== "prompt_source");
                      if (extraFields.length === 0) return null;
                      return (
                        <div className="pt-2 border-t border-border/50">
                          <p className="text-xs font-medium text-muted-foreground mb-2">Additional Metadata</p>
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            {extraFields.map(([key, value]) => (
                              <div key={key}>
                                <span className="text-muted-foreground">{key.replace(/_/g, " ")}:</span>{" "}
                                <span className="font-medium">
                                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()}

                    {/* ADR-010: Prompt Source */}
                    {summary.metadata.prompt_source && (
                      <div className="pt-2 border-t border-border/50">
                        <div className="flex items-start gap-2">
                          <GitBranch className="h-4 w-4 mt-0.5 text-muted-foreground" />
                          <div className="flex-1 space-y-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <Badge variant="outline" className="text-xs">
                                {summary.metadata.prompt_source.source === "custom" ? "Custom Prompt" :
                                 summary.metadata.prompt_source.source === "cached" ? "Cached" :
                                 summary.metadata.prompt_source.source === "default" ? "Default" : "Fallback"}
                              </Badge>
                              {summary.metadata.prompt_source.github_file_url ? (
                                <a
                                  href={summary.metadata.prompt_source.github_file_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-xs text-primary hover:underline flex items-center gap-1"
                                >
                                  View on GitHub
                                  <ExternalLink className="h-3 w-3" />
                                </a>
                              ) : (
                                <a
                                  href="/guilds"
                                  className="text-xs text-primary hover:underline flex items-center gap-1"
                                >
                                  View Default Prompts
                                  <ExternalLink className="h-3 w-3" />
                                </a>
                              )}
                            </div>
                            {summary.metadata.prompt_source.file_path && (
                              <p className="text-xs text-muted-foreground font-mono">
                                {summary.metadata.prompt_source.file_path}
                              </p>
                            )}
                            {summary.metadata.prompt_source.path_template && (
                              <p className="text-xs text-muted-foreground">
                                Template: <code className="bg-muted px-1 rounded">{summary.metadata.prompt_source.path_template}</code>
                              </p>
                            )}
                            {summary.metadata.prompt_source.resolved_variables &&
                             Object.keys(summary.metadata.prompt_source.resolved_variables).length > 0 && (
                              <p className="text-xs text-muted-foreground">
                                Variables: {Object.entries(summary.metadata.prompt_source.resolved_variables)
                                  .map(([k, v]) => `${k}=${v}`)
                                  .join(", ")}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* View Generation Details - Source Content and Prompts */}
                    {(summary.source_content || summary.prompt_system || summary.prompt_user) && (
                      <div className="pt-2 border-t border-border/50">
                        <details className="group">
                          <summary className="cursor-pointer text-xs text-primary hover:underline flex items-center gap-1">
                            <FileText className="h-3 w-3" />
                            View Generation Details
                            <span className="text-muted-foreground ml-1">(prompts & source)</span>
                          </summary>
                          <div className="mt-3 space-y-3">
                            {summary.source_content && (
                              <div>
                                <h5 className="text-xs font-medium mb-1">Source Messages</h5>
                                <pre className="text-xs bg-muted p-2 rounded max-h-40 overflow-auto whitespace-pre-wrap">
                                  {summary.source_content.slice(0, 5000)}
                                  {summary.source_content.length > 5000 && "..."}
                                </pre>
                              </div>
                            )}
                            {summary.prompt_system && (
                              <div>
                                <h5 className="text-xs font-medium mb-1">System Prompt</h5>
                                <pre className="text-xs bg-muted p-2 rounded max-h-40 overflow-auto whitespace-pre-wrap">
                                  {summary.prompt_system.slice(0, 3000)}
                                  {summary.prompt_system.length > 3000 && "..."}
                                </pre>
                              </div>
                            )}
                            {summary.prompt_user && (
                              <div>
                                <h5 className="text-xs font-medium mb-1">User Prompt</h5>
                                <pre className="text-xs bg-muted p-2 rounded max-h-40 overflow-auto whitespace-pre-wrap">
                                  {summary.prompt_user.slice(0, 3000)}
                                  {summary.prompt_user.length > 3000 && "..."}
                                </pre>
                              </div>
                            )}
                          </div>
                        </details>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          </>
        ) : summaryId ? (
          <div className="flex flex-col items-center justify-center py-12">
            <AlertCircle className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-muted-foreground">Summary not found</p>
          </div>
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
