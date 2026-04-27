/**
 * Admin Issues Page (ADR-070)
 *
 * System-wide view of locally submitted issues for administrators.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { format } from "date-fns";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
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
  Bug,
  Lightbulb,
  HelpCircle,
  RefreshCw,
  Filter,
  XCircle,
  ChevronLeft,
  ChevronRight,
  ArrowLeft,
  ExternalLink,
  MessageSquare,
} from "lucide-react";

interface Issue {
  id: string;
  guild_id: string | null;
  title: string;
  description: string;
  issue_type: "bug" | "feature" | "question";
  reporter_email: string | null;
  page_url: string | null;
  browser_info: string | null;
  app_version: string | null;
  status: "open" | "triaged" | "replicated" | "closed";
  github_issue_url: string | null;
  created_at: string;
}

interface IssueListResponse {
  issues: Issue[];
  total: number;
}

interface IssueFilters {
  status?: string;
  issue_type?: string;
  limit: number;
  offset: number;
}

const issueTypeConfig = {
  bug: { icon: Bug, label: "Bug", color: "destructive" },
  feature: { icon: Lightbulb, label: "Feature", color: "default" },
  question: { icon: HelpCircle, label: "Question", color: "secondary" },
} as const;

const statusConfig = {
  open: { label: "Open", variant: "outline" },
  triaged: { label: "Triaged", variant: "secondary" },
  replicated: { label: "On GitHub", variant: "default" },
  closed: { label: "Closed", variant: "secondary" },
} as const;

function useIssues(filters: IssueFilters) {
  return useQuery({
    queryKey: ["admin-issues", filters],
    queryFn: async (): Promise<IssueListResponse> => {
      const params = new URLSearchParams();
      if (filters.status) params.set("status", filters.status);
      if (filters.issue_type) params.set("issue_type", filters.issue_type);
      params.set("limit", String(filters.limit));
      params.set("offset", String(filters.offset));
      return api.get<IssueListResponse>(`/issues?${params.toString()}`);
    },
    staleTime: 30000,
  });
}

export function AdminIssues() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<IssueFilters>({ limit: 50, offset: 0 });
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);

  const { data, isLoading, refetch } = useIssues(filters);

  const clearFilters = () => {
    setFilters({ limit: 50, offset: 0 });
  };

  const hasActiveFilters = filters.status || filters.issue_type;

  const handlePrevPage = () => {
    setFilters((f) => ({
      ...f,
      offset: Math.max(0, f.offset - f.limit),
    }));
  };

  const handleNextPage = () => {
    if (data && filters.offset + filters.limit < data.total) {
      setFilters((f) => ({
        ...f,
        offset: f.offset + f.limit,
      }));
    }
  };

  // Count by type
  const bugCount = data?.issues.filter((i) => i.issue_type === "bug").length || 0;
  const featureCount = data?.issues.filter((i) => i.issue_type === "feature").length || 0;
  const questionCount = data?.issues.filter((i) => i.issue_type === "question").length || 0;
  const openCount = data?.issues.filter((i) => i.status === "open").length || 0;

  if (isLoading) {
    return <AdminIssuesSkeleton />;
  }

  return (
    <div className="container mx-auto py-8 px-4 space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => navigate("/guilds")}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <h1 className="text-2xl font-bold">Local Issues</h1>
            {openCount > 0 && <Badge variant="outline">{openCount} open</Badge>}
          </div>
          <p className="text-muted-foreground ml-10">
            Issues submitted via the local tracker (not GitHub)
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </motion.div>

      {/* Summary Cards */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="grid grid-cols-2 md:grid-cols-4 gap-4"
      >
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Issues</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data?.total || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Bug className="h-4 w-4" /> Bugs
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-destructive">{bugCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Lightbulb className="h-4 w-4" /> Features
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-500">{featureCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <HelpCircle className="h-4 w-4" /> Questions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-amber-500">{questionCount}</div>
          </CardContent>
        </Card>
      </motion.div>

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

              <Select
                value={filters.issue_type || "all"}
                onValueChange={(value) =>
                  setFilters((f) => ({
                    ...f,
                    issue_type: value === "all" ? undefined : value,
                    offset: 0,
                  }))
                }
              >
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="bug">Bug</SelectItem>
                  <SelectItem value="feature">Feature</SelectItem>
                  <SelectItem value="question">Question</SelectItem>
                </SelectContent>
              </Select>

              <Select
                value={filters.status || "all"}
                onValueChange={(value) =>
                  setFilters((f) => ({
                    ...f,
                    status: value === "all" ? undefined : value,
                    offset: 0,
                  }))
                }
              >
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="open">Open</SelectItem>
                  <SelectItem value="triaged">Triaged</SelectItem>
                  <SelectItem value="replicated">On GitHub</SelectItem>
                  <SelectItem value="closed">Closed</SelectItem>
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

      {/* Issues Table */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        <Card className="border-border/50">
          <CardContent className="p-0">
            {!data?.issues.length ? (
              <div className="flex flex-col items-center justify-center py-16">
                <MessageSquare className="h-12 w-12 text-muted-foreground/50 mb-4" />
                <h3 className="text-lg font-medium mb-1">No issues found</h3>
                <p className="text-muted-foreground text-center max-w-md">
                  {hasActiveFilters
                    ? "No issues match your current filters."
                    : "No local issues have been submitted yet."}
                </p>
              </div>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[180px]">Created</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>GitHub</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.issues.map((issue) => {
                      const typeConfig = issueTypeConfig[issue.issue_type];
                      const TypeIcon = typeConfig.icon;
                      return (
                        <TableRow
                          key={issue.id}
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => setSelectedIssue(issue)}
                        >
                          <TableCell className="font-mono text-xs">
                            {format(new Date(issue.created_at), "MMM d, HH:mm")}
                          </TableCell>
                          <TableCell>
                            <div className="font-medium truncate max-w-xs">{issue.title}</div>
                            {issue.page_url && (
                              <div className="text-xs text-muted-foreground truncate max-w-xs">
                                {issue.page_url}
                              </div>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <TypeIcon className="h-4 w-4" />
                              <span>{typeConfig.label}</span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant={statusConfig[issue.status]?.variant as "outline" | "secondary" | "default" || "outline"}>
                              {statusConfig[issue.status]?.label || issue.status}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {issue.github_issue_url ? (
                              <a
                                href={issue.github_issue_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-primary hover:underline flex items-center gap-1"
                              >
                                View <ExternalLink className="h-3 w-3" />
                              </a>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>

                {/* Pagination */}
                <div className="flex items-center justify-between px-4 py-3 border-t">
                  <div className="text-sm text-muted-foreground">
                    Showing {filters.offset + 1} - {Math.min(filters.offset + filters.limit, data.total)} of{" "}
                    {data.total}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handlePrevPage}
                      disabled={filters.offset === 0}
                    >
                      <ChevronLeft className="h-4 w-4" />
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleNextPage}
                      disabled={filters.offset + filters.limit >= data.total}
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

      {/* Issue Detail Dialog */}
      <Dialog open={!!selectedIssue} onOpenChange={(open) => !open && setSelectedIssue(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedIssue && (
                <>
                  {(() => {
                    const Icon = issueTypeConfig[selectedIssue.issue_type].icon;
                    return <Icon className="h-5 w-5" />;
                  })()}
                  {issueTypeConfig[selectedIssue.issue_type].label}
                </>
              )}
            </DialogTitle>
          </DialogHeader>
          {selectedIssue && (
            <div className="space-y-4">
              <div>
                <div className="text-lg font-medium">{selectedIssue.title}</div>
                <div className="text-xs text-muted-foreground">
                  ID: {selectedIssue.id} • Created: {format(new Date(selectedIssue.created_at), "PPpp")}
                </div>
              </div>

              <div>
                <div className="text-sm text-muted-foreground mb-1">Description</div>
                <div className="bg-muted p-3 rounded-md whitespace-pre-wrap text-sm">
                  {selectedIssue.description}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-sm text-muted-foreground">Status</div>
                  <Badge variant={statusConfig[selectedIssue.status]?.variant as "outline" | "secondary" | "default" || "outline"}>
                    {statusConfig[selectedIssue.status]?.label || selectedIssue.status}
                  </Badge>
                </div>
                {selectedIssue.page_url && (
                  <div>
                    <div className="text-sm text-muted-foreground">Page URL</div>
                    <a
                      href={selectedIssue.page_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline text-sm truncate block"
                    >
                      {selectedIssue.page_url}
                    </a>
                  </div>
                )}
                {selectedIssue.browser_info && (
                  <div>
                    <div className="text-sm text-muted-foreground">Browser</div>
                    <div className="text-sm">{selectedIssue.browser_info}</div>
                  </div>
                )}
                {selectedIssue.guild_id && (
                  <div>
                    <div className="text-sm text-muted-foreground">Guild</div>
                    <div className="text-sm font-mono">{selectedIssue.guild_id}</div>
                  </div>
                )}
              </div>

              {selectedIssue.github_issue_url && (
                <div className="pt-2 border-t">
                  <Button asChild variant="outline" className="w-full">
                    <a href={selectedIssue.github_issue_url} target="_blank" rel="noopener noreferrer">
                      <ExternalLink className="mr-2 h-4 w-4" />
                      View on GitHub
                    </a>
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AdminIssuesSkeleton() {
  return (
    <div className="container mx-auto py-8 px-4 space-y-6">
      <div className="flex justify-between">
        <div>
          <Skeleton className="h-8 w-48 mb-2" />
          <Skeleton className="h-4 w-64" />
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
