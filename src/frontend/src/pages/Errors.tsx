import { useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useErrors, useResolveError, useBulkResolveErrors } from "@/hooks/useErrors";
import { useToast } from "@/hooks/use-toast";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { ErrorCard } from "@/components/errors/ErrorCard";
import { ErrorDetailDrawer } from "@/components/errors/ErrorDetailDrawer";
import { AlertTriangle, RefreshCw, Filter, XCircle, X, CheckCircle2, ChevronDown } from "lucide-react";
import type { ErrorLogItem, ErrorType, ErrorSeverity, ErrorFilters } from "@/types/errors";

const errorTypes: { value: ErrorType; label: string }[] = [
  { value: "discord_permission", label: "Permission" },
  { value: "discord_not_found", label: "Not Found" },
  { value: "discord_rate_limit", label: "Rate Limit" },
  { value: "api_error", label: "API Error" },
  { value: "database_error", label: "Database" },
  { value: "summarization_error", label: "Summarization" },
  { value: "schedule_error", label: "Schedule" },
  { value: "webhook_error", label: "Webhook" },
  { value: "unknown", label: "Unknown" },
];

const severities: { value: ErrorSeverity; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "error", label: "Error" },
  { value: "warning", label: "Warning" },
  { value: "info", label: "Info" },
];

export function Errors() {
  const { id: guildId } = useParams<{ id: string }>();
  const { toast } = useToast();

  const [filters, setFilters] = useState<ErrorFilters>({
    include_resolved: false,
    limit: 100,
    error_types: [],
  });
  // Missing Access errors (discord_permission) hidden by default
  const [showMissingAccess, setShowMissingAccess] = useState(false);
  const [selectedError, setSelectedError] = useState<ErrorLogItem | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [bulkResolveType, setBulkResolveType] = useState<ErrorType | null>(null);

  const { data: rawData, isLoading, refetch } = useErrors(guildId || "", filters);

  // Filter out Missing Access errors client-side if toggle is off
  const data = rawData ? {
    ...rawData,
    errors: showMissingAccess
      ? rawData.errors
      : rawData.errors.filter(e => e.error_type !== "discord_permission"),
    unresolved_count: showMissingAccess
      ? rawData.unresolved_count
      : rawData.errors.filter(e => e.error_type !== "discord_permission" && !e.is_resolved).length,
  } : rawData;
  const resolveError = useResolveError(guildId || "");
  const bulkResolve = useBulkResolveErrors(guildId || "");

  const handleResolve = async (errorId: string, notes?: string) => {
    try {
      await resolveError.mutateAsync({ errorId, notes });
      toast({
        title: "Error resolved",
        description: "The error has been marked as resolved.",
      });
    } catch {
      toast({
        title: "Failed to resolve",
        description: "Could not resolve the error. Please try again.",
        variant: "destructive",
      });
      throw new Error("Failed to resolve error");
    }
  };

  const handleBulkResolve = async () => {
    if (!bulkResolveType) return;
    
    try {
      const result = await bulkResolve.mutateAsync({ errorType: bulkResolveType });
      toast({
        title: "Errors resolved",
        description: `${result.resolved_count} error(s) have been marked as resolved.`,
      });
      setBulkResolveType(null);
    } catch {
      toast({
        title: "Failed to resolve",
        description: "Could not resolve errors. Please try again.",
        variant: "destructive",
      });
    }
  };

  const handleErrorClick = (error: ErrorLogItem) => {
    setSelectedError(error);
    setDrawerOpen(true);
  };

  const toggleErrorType = (type: ErrorType) => {
    setFilters((f) => {
      const currentTypes = f.error_types || [];
      const isSelected = currentTypes.includes(type);
      return {
        ...f,
        error_types: isSelected
          ? currentTypes.filter((t) => t !== type)
          : [...currentTypes, type],
      };
    });
  };

  const clearFilters = () => {
    setFilters({ include_resolved: false, limit: 100, error_types: [] });
    setShowMissingAccess(false);
  };

  const hasActiveFilters = (filters.error_types && filters.error_types.length > 0) || filters.severity || showMissingAccess;

  // Get count of unresolved errors by type for bulk resolve menu
  const unresolvedByType = data?.errors.reduce((acc, err) => {
    if (!err.is_resolved) {
      acc[err.error_type] = (acc[err.error_type] || 0) + 1;
    }
    return acc;
  }, {} as Record<ErrorType, number>) || {};

  const getTypeLabel = (type: ErrorType) => 
    errorTypes.find((t) => t.value === type)?.label || type;

  if (isLoading) {
    return <ErrorsSkeleton />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">Errors</h1>
            {data && data.unresolved_count > 0 && (
              <Badge variant="destructive">{data.unresolved_count} unresolved</Badge>
            )}
          </div>
          <p className="text-muted-foreground">
            View and manage operational errors
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Bulk Resolve Dropdown */}
          {data && data.unresolved_count > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline">
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                  Bulk Resolve
                  <ChevronDown className="ml-2 h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                {Object.entries(unresolvedByType).map(([type, count]) => (
                  <DropdownMenuItem
                    key={type}
                    onClick={() => setBulkResolveType(type as ErrorType)}
                    className="justify-between"
                  >
                    <span>All {getTypeLabel(type as ErrorType)}</span>
                    <Badge variant="secondary" className="ml-2">{count as number}</Badge>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </div>
      </motion.div>

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <Card className="border-border/50">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Filters</span>
              </div>

              {/* Multi-select Type Filter */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" className="h-10">
                    Error Types
                    {filters.error_types && filters.error_types.length > 0 && (
                      <Badge variant="secondary" className="ml-2">
                        {filters.error_types.length}
                      </Badge>
                    )}
                    <ChevronDown className="ml-2 h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-48">
                  {errorTypes.map((type) => {
                    const isSelected = filters.error_types?.includes(type.value) || false;
                    return (
                      <DropdownMenuItem
                        key={type.value}
                        onClick={(e) => {
                          e.preventDefault();
                          toggleErrorType(type.value);
                        }}
                        className="justify-between cursor-pointer"
                      >
                        <span>{type.label}</span>
                        {isSelected && (
                          <CheckCircle2 className="h-4 w-4 text-primary" />
                        )}
                      </DropdownMenuItem>
                    );
                  })}
                </DropdownMenuContent>
              </DropdownMenu>

              {/* Selected type badges */}
              {filters.error_types && filters.error_types.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {filters.error_types.map((type) => (
                    <Badge
                      key={type}
                      variant="secondary"
                      className="gap-1 cursor-pointer hover:bg-secondary/80"
                      onClick={() => toggleErrorType(type)}
                    >
                      {getTypeLabel(type)}
                      <X className="h-3 w-3" />
                    </Badge>
                  ))}
                </div>
              )}

              <Select
                value={filters.severity || "all"}
                onValueChange={(value) =>
                  setFilters((f) => ({
                    ...f,
                    severity: value === "all" ? undefined : (value as ErrorSeverity),
                  }))
                }
              >
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Severity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Severity</SelectItem>
                  {severities.map((sev) => (
                    <SelectItem key={sev.value} value={sev.value}>
                      {sev.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <div className="flex items-center gap-2">
                <Switch
                  id="show-missing-access"
                  checked={showMissingAccess}
                  onCheckedChange={setShowMissingAccess}
                />
                <Label htmlFor="show-missing-access" className="text-sm">
                  Show Missing Access
                </Label>
              </div>

              <div className="flex items-center gap-2">
                <Switch
                  id="show-resolved"
                  checked={filters.include_resolved || false}
                  onCheckedChange={(checked) =>
                    setFilters((f) => ({ ...f, include_resolved: checked }))
                  }
                />
                <Label htmlFor="show-resolved" className="text-sm">
                  Show resolved
                </Label>
              </div>

              {hasActiveFilters && (
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  <XCircle className="mr-1 h-4 w-4" />
                  Clear
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Error List */}
      {!data?.errors.length ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
        >
          <Card className="border-border/50">
            <CardContent className="flex flex-col items-center justify-center py-16">
              <AlertTriangle className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <h3 className="text-lg font-medium mb-1">No errors found</h3>
              <p className="text-muted-foreground text-center max-w-md">
                {hasActiveFilters
                  ? "No errors match your current filters. Try adjusting or clearing them."
                  : filters.include_resolved
                  ? "Great news! There are no errors to display."
                  : "No unresolved errors. Toggle 'Show resolved' to see past errors."}
              </p>
            </CardContent>
          </Card>
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="space-y-2"
        >
          {data.errors.map((error, index) => (
            <ErrorCard
              key={error.id}
              error={error}
              index={index}
              onClick={() => handleErrorClick(error)}
            />
          ))}
          {data.total > (filters.limit || 100) && (
            <p className="text-center text-sm text-muted-foreground pt-4">
              Showing {data.errors.length} of {data.total} errors
            </p>
          )}
        </motion.div>
      )}

      {/* Error Detail Drawer/Dialog */}
      <ErrorDetailDrawer
        error={selectedError}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        onResolve={handleResolve}
        isResolving={resolveError.isPending}
      />

      {/* Bulk Resolve Confirmation Dialog */}
      <AlertDialog open={!!bulkResolveType} onOpenChange={(open) => !open && setBulkResolveType(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Resolve all {bulkResolveType && getTypeLabel(bulkResolveType)} errors?</AlertDialogTitle>
            <AlertDialogDescription>
              This will mark {bulkResolveType && unresolvedByType[bulkResolveType]} unresolved{" "}
              {bulkResolveType && getTypeLabel(bulkResolveType)} error(s) as resolved.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleBulkResolve}
              disabled={bulkResolve.isPending}
            >
              {bulkResolve.isPending ? "Resolving..." : "Resolve All"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function ErrorsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between">
        <div>
          <Skeleton className="h-8 w-32 mb-2" />
          <Skeleton className="h-4 w-48" />
        </div>
        <Skeleton className="h-10 w-28" />
      </div>
      <Card className="border-border/50">
        <CardContent className="p-4">
          <div className="flex gap-4">
            <Skeleton className="h-10 w-40" />
            <Skeleton className="h-10 w-32" />
            <Skeleton className="h-6 w-32" />
          </div>
        </CardContent>
      </Card>
      <div className="space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-20 w-full rounded-lg" />
        ))}
      </div>
    </div>
  );
}