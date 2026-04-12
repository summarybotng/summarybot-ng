import { useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { format } from "date-fns";
import { useAuditLogs, useAuditSummary } from "@/hooks/useAuditLog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Shield,
  RefreshCw,
  Filter,
  XCircle,
  CheckCircle,
  AlertTriangle,
  User,
  Clock,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import type { AuditLogEntry, AuditFilters, AuditCategory, AuditSeverity } from "@/types/audit";

const categories: { value: AuditCategory; label: string }[] = [
  { value: "auth", label: "Authentication" },
  { value: "access", label: "Access" },
  { value: "action", label: "Actions" },
  { value: "source", label: "Sources" },
  { value: "admin", label: "Admin" },
  { value: "system", label: "System" },
];

const severities: { value: AuditSeverity; label: string; color: string }[] = [
  { value: "debug", label: "Debug", color: "secondary" },
  { value: "info", label: "Info", color: "default" },
  { value: "notice", label: "Notice", color: "secondary" },
  { value: "warning", label: "Warning", color: "warning" },
  { value: "alert", label: "Alert", color: "destructive" },
];

function getSeverityBadge(severity: AuditSeverity) {
  const config = severities.find(s => s.value === severity);
  const variant = config?.color === "destructive" ? "destructive"
    : config?.color === "warning" ? "outline"
    : "secondary";
  return <Badge variant={variant}>{severity}</Badge>;
}

function getCategoryLabel(category: AuditCategory) {
  return categories.find(c => c.value === category)?.label || category;
}

export function AuditLog() {
  const { id: guildId } = useParams<{ id: string }>();
  const [filters, setFilters] = useState<AuditFilters>({ limit: 50, offset: 0 });
  const [selectedEntry, setSelectedEntry] = useState<AuditLogEntry | null>(null);

  const { data, isLoading, refetch } = useAuditLogs(guildId || "", filters);
  const { data: summary } = useAuditSummary(guildId || "");

  const clearFilters = () => {
    setFilters({ limit: 50, offset: 0 });
  };

  const hasActiveFilters = filters.category || filters.severity || filters.event_type || filters.success !== undefined;

  const handlePrevPage = () => {
    setFilters(f => ({
      ...f,
      offset: Math.max(0, (f.offset || 0) - (f.limit || 50))
    }));
  };

  const handleNextPage = () => {
    if (data && (filters.offset || 0) + (filters.limit || 50) < data.total) {
      setFilters(f => ({
        ...f,
        offset: (f.offset || 0) + (f.limit || 50)
      }));
    }
  };

  if (isLoading) {
    return <AuditLogSkeleton />;
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
            <h1 className="text-2xl font-bold">Audit Log</h1>
            {summary && summary.alert_count > 0 && (
              <Badge variant="destructive">{summary.alert_count} alerts</Badge>
            )}
          </div>
          <p className="text-muted-foreground">
            Track user activity and security events
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </motion.div>

      {/* Summary Cards */}
      {summary && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-4"
        >
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total Events
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.total_count.toLocaleString()}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Failed Actions
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-destructive">
                {summary.failed_count.toLocaleString()}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Security Alerts
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-orange-500">
                {summary.alert_count.toLocaleString()}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Unique Users
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {Object.keys(summary.by_user).length.toLocaleString()}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <Card className="border-border/50">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Filters</span>
              </div>

              <Input
                placeholder="Event type (e.g., auth.*)"
                value={filters.event_type || ""}
                onChange={(e) => setFilters(f => ({ ...f, event_type: e.target.value || undefined, offset: 0 }))}
                className="w-48"
              />

              <Select
                value={filters.category || "all"}
                onValueChange={(value) =>
                  setFilters(f => ({
                    ...f,
                    category: value === "all" ? undefined : (value as AuditCategory),
                    offset: 0,
                  }))
                }
              >
                <SelectTrigger className="w-[150px]">
                  <SelectValue placeholder="Category" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Categories</SelectItem>
                  {categories.map((cat) => (
                    <SelectItem key={cat.value} value={cat.value}>
                      {cat.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select
                value={filters.severity || "all"}
                onValueChange={(value) =>
                  setFilters(f => ({
                    ...f,
                    severity: value === "all" ? undefined : (value as AuditSeverity),
                    offset: 0,
                  }))
                }
              >
                <SelectTrigger className="w-[130px]">
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

              <Select
                value={filters.success === undefined ? "all" : String(filters.success)}
                onValueChange={(value) =>
                  setFilters(f => ({
                    ...f,
                    success: value === "all" ? undefined : value === "true",
                    offset: 0,
                  }))
                }
              >
                <SelectTrigger className="w-[120px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="true">Success</SelectItem>
                  <SelectItem value="false">Failed</SelectItem>
                </SelectContent>
              </Select>

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

      {/* Audit Log Table */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        <Card className="border-border/50">
          <CardContent className="p-0">
            {!data?.items.length ? (
              <div className="flex flex-col items-center justify-center py-16">
                <Shield className="h-12 w-12 text-muted-foreground/50 mb-4" />
                <h3 className="text-lg font-medium mb-1">No audit logs found</h3>
                <p className="text-muted-foreground text-center max-w-md">
                  {hasActiveFilters
                    ? "No events match your current filters."
                    : "No audit events have been recorded yet."}
                </p>
              </div>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[180px]">Timestamp</TableHead>
                      <TableHead>Event</TableHead>
                      <TableHead>User</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="w-[100px]">Severity</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((entry) => (
                      <TableRow
                        key={entry.id}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => setSelectedEntry(entry)}
                      >
                        <TableCell className="font-mono text-xs">
                          {format(new Date(entry.timestamp), "MMM d, HH:mm:ss")}
                        </TableCell>
                        <TableCell>
                          <div className="font-medium">{entry.event_type}</div>
                          {entry.resource_type && (
                            <div className="text-xs text-muted-foreground">
                              {entry.resource_type}
                              {entry.resource_id && `: ${entry.resource_id.slice(0, 8)}...`}
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          {entry.user_name ? (
                            <div className="flex items-center gap-2">
                              <User className="h-4 w-4 text-muted-foreground" />
                              <span>{entry.user_name}</span>
                            </div>
                          ) : (
                            <span className="text-muted-foreground">System</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{getCategoryLabel(entry.category)}</Badge>
                        </TableCell>
                        <TableCell>
                          {entry.success ? (
                            <CheckCircle className="h-4 w-4 text-green-500" />
                          ) : (
                            <AlertTriangle className="h-4 w-4 text-destructive" />
                          )}
                        </TableCell>
                        <TableCell>{getSeverityBadge(entry.severity)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                {/* Pagination */}
                <div className="flex items-center justify-between px-4 py-3 border-t">
                  <div className="text-sm text-muted-foreground">
                    Showing {(filters.offset || 0) + 1} - {Math.min((filters.offset || 0) + (filters.limit || 50), data.total)} of {data.total}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handlePrevPage}
                      disabled={(filters.offset || 0) === 0}
                    >
                      <ChevronLeft className="h-4 w-4" />
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleNextPage}
                      disabled={(filters.offset || 0) + (filters.limit || 50) >= data.total}
                    >
                      Next
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Entry Detail Dialog */}
      <Dialog open={!!selectedEntry} onOpenChange={(open) => !open && setSelectedEntry(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Audit Log Entry</DialogTitle>
          </DialogHeader>
          {selectedEntry && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-sm text-muted-foreground">Event Type</div>
                  <div className="font-medium">{selectedEntry.event_type}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Timestamp</div>
                  <div className="font-medium flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    {format(new Date(selectedEntry.timestamp), "PPpp")}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">User</div>
                  <div className="font-medium">
                    {selectedEntry.user_name || "System"}
                    {selectedEntry.user_id && (
                      <span className="text-xs text-muted-foreground ml-2">
                        ({selectedEntry.user_id})
                      </span>
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Category</div>
                  <Badge variant="outline">{getCategoryLabel(selectedEntry.category)}</Badge>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Status</div>
                  <div className="flex items-center gap-2">
                    {selectedEntry.success ? (
                      <>
                        <CheckCircle className="h-4 w-4 text-green-500" />
                        <span>Success</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="h-4 w-4 text-destructive" />
                        <span>Failed</span>
                      </>
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Severity</div>
                  {getSeverityBadge(selectedEntry.severity)}
                </div>
              </div>

              {selectedEntry.resource_type && (
                <div>
                  <div className="text-sm text-muted-foreground">Resource</div>
                  <div className="font-medium">
                    {selectedEntry.resource_type}
                    {selectedEntry.resource_id && `: ${selectedEntry.resource_id}`}
                    {selectedEntry.resource_name && ` (${selectedEntry.resource_name})`}
                  </div>
                </div>
              )}

              {selectedEntry.error_message && (
                <div>
                  <div className="text-sm text-muted-foreground">Error Message</div>
                  <div className="font-mono text-sm bg-destructive/10 p-2 rounded text-destructive">
                    {selectedEntry.error_message}
                  </div>
                </div>
              )}

              {selectedEntry.details && Object.keys(selectedEntry.details).length > 0 && (
                <div>
                  <div className="text-sm text-muted-foreground mb-2">Details</div>
                  <pre className="font-mono text-xs bg-muted p-3 rounded overflow-auto max-h-48">
                    {JSON.stringify(selectedEntry.details, null, 2)}
                  </pre>
                </div>
              )}

              {selectedEntry.duration_ms && (
                <div className="text-sm text-muted-foreground">
                  Duration: {selectedEntry.duration_ms}ms
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AuditLogSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between">
        <div>
          <Skeleton className="h-8 w-32 mb-2" />
          <Skeleton className="h-4 w-48" />
        </div>
        <Skeleton className="h-10 w-28" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="border-border/50">
        <CardContent className="p-4">
          <div className="flex gap-4">
            <Skeleton className="h-10 w-40" />
            <Skeleton className="h-10 w-32" />
            <Skeleton className="h-10 w-32" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-0">
          <div className="space-y-2 p-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
