import { useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useToast } from "@/hooks/use-toast";
import {
  BookOpen,
  Search,
  FolderTree,
  FileText,
  Users,
  HelpCircle,
  Clock,
  AlertTriangle,
  ChevronRight,
  ExternalLink,
  RefreshCw,
  Loader2,
  Sparkles,
  Code,
  Eye,
  Copy,
  Check,
  Link2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/api/client";

interface WikiPage {
  id: string;
  path: string;
  title: string;
  content: string;  // Raw updates
  topics: string[];
  source_refs: string[];
  inbound_links: number;
  outbound_links: number;
  confidence: number;
  created_at: string;
  updated_at: string;
  // ADR-063: Synthesis fields
  synthesis: string | null;
  synthesis_updated_at: string | null;
  synthesis_source_count: number;
}

interface WikiPageSummary {
  id: string;
  path: string;
  title: string;
  topics: string[];
  updated_at: string;
  inbound_links: number;
  confidence: number;
}

interface WikiTreeNode {
  path: string;
  title: string;
  children: WikiTreeNode[];
  page_count: number;
}

interface WikiTree {
  guild_id: string;
  categories: WikiTreeNode[];
}

interface WikiSearchResult {
  query: string;
  total: number;
  pages: WikiPageSummary[];
  synthesis?: string;
  gaps: string[];
}

// Fetch wiki tree
async function fetchWikiTree(guildId: string): Promise<WikiTree> {
  return api.get<WikiTree>(`/guilds/${guildId}/wiki/tree`);
}

// Fetch wiki page
async function fetchWikiPage(guildId: string, path: string): Promise<WikiPage> {
  return api.get<WikiPage>(`/guilds/${guildId}/wiki/pages/${path}`);
}

// Search wiki
async function searchWiki(guildId: string, query: string): Promise<WikiSearchResult> {
  return api.get<WikiSearchResult>(`/guilds/${guildId}/wiki/search?q=${encodeURIComponent(query)}&synthesize=true`);
}

// Fetch recent changes
async function fetchRecentChanges(guildId: string): Promise<WikiPageSummary[]> {
  const result = await api.get<{ changes: WikiPageSummary[] }>(`/guilds/${guildId}/wiki/recent`);
  return result.changes;
}

// Fetch wiki stats
interface WikiStats {
  total_pages: number;
  total_sources: number;
  categories: Record<string, number>;
}

async function fetchWikiStats(guildId: string): Promise<WikiStats> {
  return api.get<WikiStats>(`/guilds/${guildId}/wiki/stats`);
}

// Fetch pages by source
interface WikiSourceResult {
  source_id: string;
  pages: WikiPageSummary[];
}

async function fetchSourceReferences(guildId: string, sourceId: string): Promise<WikiSourceResult> {
  return api.get<WikiSourceResult>(`/guilds/${guildId}/wiki/sources/${sourceId}`);
}

// Populate wiki from summaries
interface PopulateResult {
  summaries_processed: number;
  pages_created: number;
  pages_updated: number;
  errors: string[];
}

async function populateWiki(guildId: string, days: number = 30): Promise<PopulateResult> {
  return api.post<PopulateResult>(`/guilds/${guildId}/wiki/populate`, { days });
}

// Clear wiki
interface ClearWikiResult {
  pages_deleted: number;
  sources_deleted: number;
}

async function clearWiki(guildId: string): Promise<ClearWikiResult> {
  return api.delete<ClearWikiResult>(`/guilds/${guildId}/wiki`);
}

function WikiNavTree({ tree, currentPath }: { tree: WikiTree; currentPath?: string }) {
  const { id: guildId } = useParams<{ id: string }>();

  const categoryIcons: Record<string, React.ReactNode> = {
    topics: <FolderTree className="h-4 w-4" />,
    decisions: <FileText className="h-4 w-4" />,
    processes: <Clock className="h-4 w-4" />,
    experts: <Users className="h-4 w-4" />,
    questions: <HelpCircle className="h-4 w-4" />,
  };

  return (
    <ScrollArea className="h-[calc(100vh-200px)]">
      <nav className="space-y-2 pr-4">
        {tree.categories.map((category) => (
          <div key={category.path} className="space-y-1">
            <div className="flex items-center gap-2 py-1.5 text-sm font-medium text-muted-foreground">
              {categoryIcons[category.path] || <FolderTree className="h-4 w-4" />}
              <span className="capitalize">{category.title}</span>
              <Badge variant="secondary" className="ml-auto text-xs">
                {category.page_count}
              </Badge>
            </div>
            {category.children.map((child) => (
              <Link
                key={child.path}
                to={`/guilds/${guildId}/wiki/${child.path}`}
                className={`block pl-6 py-1 text-sm rounded-md hover:bg-accent ${
                  currentPath === child.path ? "bg-accent font-medium" : ""
                }`}
              >
                {child.title}
              </Link>
            ))}
          </div>
        ))}
      </nav>
    </ScrollArea>
  );
}

// Synthesize wiki page
async function synthesizeWikiPage(guildId: string, path: string): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>(`/guilds/${guildId}/wiki/pages/${path}/synthesize`);
}

function WikiPageView({ page }: { page: WikiPage }) {
  const { id: guildId } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"synthesis" | "updates">(page.synthesis ? "synthesis" : "updates");
  const [copied, setCopied] = useState(false);
  const { toast } = useToast();

  // Parse path for breadcrumb
  const pathParts = page.path.split("/");
  const category = pathParts[0];

  // Pre-process content to convert [source:summary-xxx] to links
  const processedContent = page.content
    .replace(/\[source:(summary-[\w-]+)\]/g, '[📄 source](?source=$1)')
    .replace(/## Update from (summary-[\w-]+)/g, '## 📝 Update from [$1](?source=$1)');

  // Regenerate synthesis mutation
  const synthesizeMutation = useMutation({
    mutationFn: () => synthesizeWikiPage(guildId!, page.path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["wiki-page", guildId, page.path] });
      toast({ title: "Synthesis regenerated" });
    },
    onError: () => {
      toast({ title: "Failed to generate synthesis", variant: "destructive" });
    },
  });

  // Copy page URL to clipboard
  const handleShare = async () => {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      toast({
        title: "Link copied!",
        description: "Wiki page URL copied to clipboard",
      });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({
        title: "Copy failed",
        description: "Please copy the URL manually",
        variant: "destructive",
      });
    }
  };

  // Handle wiki internal links
  const handleLink = (href: string) => {
    if (href.startsWith("?source=")) {
      const sourceId = href.replace("?source=", "");
      return `/guilds/${guildId}/wiki?source=${sourceId}`;
    }
    if (href.startsWith("topics/") || href.startsWith("decisions/") ||
        href.startsWith("processes/") || href.startsWith("experts/") ||
        href.startsWith("questions/")) {
      return `/guilds/${guildId}/wiki/${href}`;
    }
    return href;
  };

  const isSourceLink = (href: string) => href.startsWith("?source=");

  // Markdown renderer component
  const MarkdownContent = ({ content }: { content: string }) => (
    <article className="prose prose-slate dark:prose-invert max-w-none
      prose-headings:font-bold prose-headings:tracking-tight
      prose-h1:text-2xl prose-h1:border-b prose-h1:pb-2 prose-h1:mb-4
      prose-h2:text-xl prose-h2:mt-8 prose-h2:mb-4
      prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
      prose-p:leading-7 prose-p:mb-4
      prose-ul:my-4 prose-ul:list-disc prose-ul:pl-6
      prose-ol:my-4 prose-ol:list-decimal prose-ol:pl-6
      prose-li:my-1
      prose-a:text-primary prose-a:underline prose-a:underline-offset-2 hover:prose-a:text-primary/80
      prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm
      prose-pre:bg-muted prose-pre:p-4 prose-pre:rounded-lg
      prose-blockquote:border-l-4 prose-blockquote:border-primary prose-blockquote:pl-4 prose-blockquote:italic
      prose-strong:font-bold
      prose-table:border-collapse prose-th:border prose-th:p-2 prose-td:border prose-td:p-2
    ">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const isExternal = href?.startsWith('http');
            const isSource = href ? isSourceLink(href) : false;
            const finalHref = href ? handleLink(href) : '#';

            if (isExternal) {
              return (
                <a href={finalHref} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1">
                  {children}
                  <ExternalLink className="h-3 w-3" />
                </a>
              );
            }

            if (isSource) {
              return (
                <Link
                  to={finalHref}
                  className="inline-flex items-center gap-1 text-xs bg-muted px-2 py-0.5 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted/80 no-underline font-mono"
                >
                  {children}
                </Link>
              );
            }

            return <Link to={finalHref}>{children}</Link>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </article>
  );

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to={`/guilds/${guildId}/wiki`}>Wiki</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to={`/guilds/${guildId}/wiki`} className="capitalize">{category}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{page.title}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Title and Actions */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{page.title}</h1>
        <div className="flex gap-2">
          {activeTab === "synthesis" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => synthesizeMutation.mutate()}
              disabled={synthesizeMutation.isPending}
            >
              {synthesizeMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-1" />
              )}
              Regenerate
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleShare}>
            {copied ? (
              <>
                <Check className="h-4 w-4 mr-1" />
                Copied!
              </>
            ) : (
              <>
                <Link2 className="h-4 w-4 mr-1" />
                Share
              </>
            )}
          </Button>
        </div>
      </div>

      {/* ADR-063: Tabs for Synthesis and Updates */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "synthesis" | "updates")}>
        <TabsList>
          <TabsTrigger value="synthesis" className="gap-2">
            <Sparkles className="h-4 w-4" />
            Synthesis
            {page.synthesis && (
              <Badge variant="secondary" className="ml-1 text-xs">
                {page.synthesis_source_count} sources
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="updates" className="gap-2">
            <FileText className="h-4 w-4" />
            Updates
            <Badge variant="outline" className="ml-1 text-xs">
              {page.source_refs.length}
            </Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="synthesis" className="mt-4">
          {page.synthesis ? (
            <Card>
              <CardContent className="pt-6">
                <MarkdownContent content={page.synthesis} />
                {page.synthesis_updated_at && (
                  <div className="mt-4 pt-4 border-t text-sm text-muted-foreground">
                    Last synthesized: {new Date(page.synthesis_updated_at).toLocaleString()}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <Sparkles className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="font-medium mb-2">No synthesis yet</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Generate an AI summary of all updates on this page
                </p>
                <Button
                  onClick={() => synthesizeMutation.mutate()}
                  disabled={synthesizeMutation.isPending}
                >
                  {synthesizeMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4 mr-2" />
                  )}
                  Generate Synthesis
                </Button>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="updates" className="mt-4">
          <Card>
            <CardContent className="pt-6">
              <MarkdownContent content={processedContent} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Page info */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Sources</div>
            <div className="text-2xl font-bold">{page.source_refs.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Links</div>
            <div className="text-2xl font-bold">
              {page.inbound_links + page.outbound_links}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Updated</div>
            <div className="text-2xl font-bold">
              {page.updated_at
                ? new Date(page.updated_at).toLocaleDateString()
                : "—"}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Confidence</div>
            <div className="text-2xl font-bold">{page.confidence}%</div>
          </CardContent>
        </Card>
      </div>

      {/* Topics */}
      {page.topics.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {page.topics.map((topic) => (
            <Badge key={topic} variant="secondary">
              {topic}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function WikiSearch({ guildId }: { guildId: string }) {
  const [query, setQuery] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const activeQuery = searchParams.get("q") || "";

  const { data: results, isLoading } = useQuery({
    queryKey: ["wiki-search", guildId, activeQuery],
    queryFn: () => searchWiki(guildId, activeQuery),
    enabled: !!activeQuery,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      setSearchParams({ q: query.trim() });
    }
  };

  return (
    <div className="space-y-6">
      {/* Search form */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <Input
          placeholder="Search wiki..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1"
        />
        <Button type="submit">
          <Search className="h-4 w-4 mr-2" />
          Search
        </Button>
      </form>

      {/* Results */}
      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {results && (
        <div className="space-y-6">
          {/* AI synthesis */}
          {results.synthesis && (
            <Card className="border-primary/50">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <BookOpen className="h-4 w-4" />
                  AI Answer
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p>{results.synthesis}</p>
              </CardContent>
            </Card>
          )}

          {/* Page results */}
          <div className="space-y-2">
            <h3 className="font-medium">
              {results.total} page{results.total !== 1 ? "s" : ""} found
            </h3>
            {results.pages.map((page) => (
              <Link
                key={page.id}
                to={`/guilds/${guildId}/wiki/${page.path}`}
                className="block"
              >
                <Card className="hover:bg-accent/50 transition-colors">
                  <CardContent className="py-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="font-medium">{page.title}</h4>
                        <p className="text-sm text-muted-foreground">
                          {page.path}
                        </p>
                      </div>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>

          {/* Knowledge gaps */}
          {results.gaps.length > 0 && (
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Knowledge Gaps Detected</AlertTitle>
              <AlertDescription>
                <ul className="list-disc list-inside mt-2">
                  {results.gaps.map((gap, i) => (
                    <li key={i}>{gap}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}
        </div>
      )}
    </div>
  );
}

function SourceReferences({ guildId, sourceId }: { guildId: string; sourceId: string }) {
  const { data: result, isLoading, error } = useQuery({
    queryKey: ["wiki-source", guildId, sourceId],
    queryFn: () => fetchSourceReferences(guildId, sourceId),
  });

  // Extract summary ID from source ID (e.g., "summary-abc123" -> "abc123")
  const summaryId = sourceId.startsWith("summary-") ? sourceId.slice(8) : null;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Error loading source</AlertTitle>
        <AlertDescription>
          Could not load pages for this source.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Source info */}
      <Card className="border-primary/50">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <FileText className="h-4 w-4" />
              Source Reference
            </span>
            {summaryId && (
              <Link to={`/guilds/${guildId}/summaries?view=${summaryId}`}>
                <Button variant="outline" size="sm">
                  <ExternalLink className="h-4 w-4 mr-1" />
                  View Summary
                </Button>
              </Link>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <code className="text-sm bg-muted px-2 py-1 rounded">{sourceId}</code>
          <p className="text-sm text-muted-foreground mt-2">
            {result?.pages.length || 0} page{result?.pages.length !== 1 ? "s" : ""} reference this source
          </p>
        </CardContent>
      </Card>

      {/* Page results */}
      <div className="space-y-2">
        <h3 className="font-medium">Pages using this source</h3>
        {result?.pages.map((page) => (
          <Link
            key={page.id}
            to={`/guilds/${guildId}/wiki/${page.path}`}
            className="block"
          >
            <Card className="hover:bg-accent/50 transition-colors">
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-medium">{page.title}</h4>
                    <p className="text-sm text-muted-foreground">
                      {page.path}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
        {result?.pages.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">
            No pages reference this source
          </p>
        )}
      </div>
    </div>
  );
}

function RecentChanges({ guildId }: { guildId: string }) {
  const { data: changes, isLoading } = useQuery({
    queryKey: ["wiki-recent", guildId],
    queryFn: () => fetchRecentChanges(guildId),
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {changes?.map((page) => (
        <Link
          key={page.id}
          to={`/guilds/${guildId}/wiki/${page.path}`}
          className="block"
        >
          <Card className="hover:bg-accent/50 transition-colors">
            <CardContent className="py-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium">{page.title}</span>
                  <span className="text-sm text-muted-foreground ml-2">
                    {page.updated_at
                      ? new Date(page.updated_at).toLocaleDateString()
                      : ""}
                  </span>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
        </Link>
      ))}
      {(!changes || changes.length === 0) && (
        <p className="text-sm text-muted-foreground text-center py-8">
          No recent changes
        </p>
      )}
    </div>
  );
}

function PopulateWiki({ guildId }: { guildId: string }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Fetch stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["wiki-stats", guildId],
    queryFn: () => fetchWikiStats(guildId),
  });

  // Populate mutation
  const populateMutation = useMutation({
    mutationFn: (days: number) => populateWiki(guildId, days),
    onSuccess: () => {
      // Invalidate all wiki queries to refresh
      queryClient.invalidateQueries({ queryKey: ["wiki-tree", guildId] });
      queryClient.invalidateQueries({ queryKey: ["wiki-stats", guildId] });
      queryClient.invalidateQueries({ queryKey: ["wiki-recent", guildId] });
    },
  });

  // Clear wiki mutation
  const clearMutation = useMutation({
    mutationFn: () => clearWiki(guildId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["wiki-tree", guildId] });
      queryClient.invalidateQueries({ queryKey: ["wiki-stats", guildId] });
      queryClient.invalidateQueries({ queryKey: ["wiki-recent", guildId] });
      setShowClearConfirm(false);
      toast({
        title: "Wiki cleared",
        description: `Deleted ${data.pages_deleted} pages and ${data.sources_deleted} sources`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to clear wiki",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  return (
    <div className="space-y-6">
      {/* Stats Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            Wiki Statistics
          </CardTitle>
        </CardHeader>
        <CardContent>
          {statsLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </div>
          ) : stats ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-2xl font-bold">{stats.total_pages}</div>
                <div className="text-sm text-muted-foreground">Total Pages</div>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-2xl font-bold">{stats.total_sources}</div>
                <div className="text-sm text-muted-foreground">Sources</div>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-2xl font-bold">{stats.categories?.topics || 0}</div>
                <div className="text-sm text-muted-foreground">Topics</div>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <div className="text-2xl font-bold">{stats.categories?.decisions || 0}</div>
                <div className="text-sm text-muted-foreground">Decisions</div>
              </div>
            </div>
          ) : (
            <p className="text-muted-foreground">No wiki data yet</p>
          )}
        </CardContent>
      </Card>

      {/* Populate Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Populate Wiki
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Populate the wiki from your existing summaries. This will analyze your
            summaries and create wiki pages for topics, decisions, and expertise.
          </p>

          {populateMutation.isSuccess && (
            <Alert>
              <Sparkles className="h-4 w-4" />
              <AlertTitle>Population Complete</AlertTitle>
              <AlertDescription>
                Processed {populateMutation.data?.summaries_processed} summaries.
                Created {populateMutation.data?.pages_created} pages,
                updated {populateMutation.data?.pages_updated} pages.
                {populateMutation.data?.errors?.length > 0 && (
                  <span className="text-yellow-600">
                    {" "}({populateMutation.data.errors.length} errors)
                  </span>
                )}
              </AlertDescription>
            </Alert>
          )}

          {populateMutation.isError && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Population Failed</AlertTitle>
              <AlertDescription>
                {(populateMutation.error as Error)?.message || "Unknown error"}
              </AlertDescription>
            </Alert>
          )}

          <div className="flex gap-2">
            <Button
              onClick={() => populateMutation.mutate(30)}
              disabled={populateMutation.isPending}
            >
              {populateMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Populate from Last 30 Days
            </Button>
            <Button
              variant="outline"
              onClick={() => populateMutation.mutate(90)}
              disabled={populateMutation.isPending}
            >
              Last 90 Days
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Clear Wiki Card */}
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Clear Wiki
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Delete all wiki pages and sources. This action cannot be undone.
            You can repopulate the wiki afterwards from your summaries.
          </p>

          {!showClearConfirm ? (
            <Button
              variant="destructive"
              onClick={() => setShowClearConfirm(true)}
              disabled={clearMutation.isPending || !stats?.total_pages}
            >
              Clear All Wiki Data
            </Button>
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-medium text-destructive">
                Are you sure? This will delete {stats?.total_pages || 0} pages and {stats?.total_sources || 0} sources.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  onClick={() => clearMutation.mutate()}
                  disabled={clearMutation.isPending}
                >
                  {clearMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : null}
                  Yes, Clear Everything
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowClearConfirm(false)}
                  disabled={clearMutation.isPending}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function Wiki() {
  const { id: guildId, "*": pagePath } = useParams<{ id: string; "*": string }>();
  const [searchParams] = useSearchParams();
  const searchQuery = searchParams.get("q");
  const sourceId = searchParams.get("source");

  // Fetch tree
  const { data: tree, isLoading: treeLoading } = useQuery({
    queryKey: ["wiki-tree", guildId],
    queryFn: () => fetchWikiTree(guildId!),
    enabled: !!guildId,
  });

  // Fetch page if path is provided (and not just viewing source/search)
  const hasValidPath = !!pagePath && pagePath.length > 0 && pagePath !== "undefined";
  const { data: page, isLoading: pageLoading } = useQuery({
    queryKey: ["wiki-page", guildId, pagePath],
    queryFn: () => fetchWikiPage(guildId!, pagePath!),
    enabled: !!guildId && hasValidPath && !sourceId && !searchQuery,
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">Wiki</h1>
        </div>
        <Link to={`/guilds/${guildId}/wiki?q=`}>
          <Button variant="outline">
            <Search className="h-4 w-4 mr-2" />
            Search
          </Button>
        </Link>
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sidebar */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Navigation</CardTitle>
          </CardHeader>
          <CardContent>
            {treeLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-3/4" />
                <Skeleton className="h-6 w-1/2" />
              </div>
            ) : tree ? (
              <WikiNavTree tree={tree} currentPath={pagePath} />
            ) : (
              <p className="text-sm text-muted-foreground">
                No wiki pages yet
              </p>
            )}
          </CardContent>
        </Card>

        {/* Content */}
        <div className="lg:col-span-3">
          {sourceId ? (
            <SourceReferences guildId={guildId!} sourceId={sourceId} />
          ) : searchQuery ? (
            <WikiSearch guildId={guildId!} />
          ) : pagePath ? (
            pageLoading ? (
              <div className="space-y-4">
                <Skeleton className="h-8 w-1/2" />
                <Skeleton className="h-64 w-full" />
              </div>
            ) : page ? (
              <WikiPageView page={page} />
            ) : (
              <Card>
                <CardContent className="py-12 text-center">
                  <p className="text-muted-foreground">Page not found</p>
                </CardContent>
              </Card>
            )
          ) : (
            <Tabs defaultValue="recent">
              <TabsList>
                <TabsTrigger value="recent">Recent Changes</TabsTrigger>
                <TabsTrigger value="browse">Browse</TabsTrigger>
                <TabsTrigger value="populate">Populate</TabsTrigger>
              </TabsList>
              <TabsContent value="recent" className="mt-4">
                <RecentChanges guildId={guildId!} />
              </TabsContent>
              <TabsContent value="browse" className="mt-4">
                <Card>
                  <CardContent className="py-8 text-center">
                    <BookOpen className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <h3 className="font-medium mb-2">
                      Browse the Knowledge Base
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      Select a category from the navigation to explore wiki
                      pages
                    </p>
                  </CardContent>
                </Card>
              </TabsContent>
              <TabsContent value="populate" className="mt-4">
                <PopulateWiki guildId={guildId!} />
              </TabsContent>
            </Tabs>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default Wiki;
