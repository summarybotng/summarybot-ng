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
  Star,
  Filter,
  SlidersHorizontal,
  X,
  Cpu,
  Play,
  Square,
  Settings2,
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { api } from "@/api/client";

interface SourceMetadata {
  id: string;
  title: string;
  source_type: string;
  ingested_at: string | null;
}

interface LinkedPage {
  path: string;
  title: string;
  link_text: string | null;
}

interface WikiPage {
  id: string;
  path: string;
  title: string;
  content: string;  // Raw updates
  topics: string[];
  source_refs: string[];
  source_metadata: SourceMetadata[];  // Readable titles for sources
  inbound_links: number;
  outbound_links: number;
  linked_pages_from: LinkedPage[];  // Pages this page links to
  linked_pages_to: LinkedPage[];    // Pages that link to this page
  confidence: number;
  created_at: string;
  updated_at: string;
  // ADR-063: Synthesis fields
  synthesis: string | null;
  synthesis_updated_at: string | null;
  synthesis_source_count: number;
  // ADR-064/065: Rating and model tracking
  synthesis_model: string | null;
  average_rating: number | null;
  rating_count: number;
}

interface WikiPageSummary {
  id: string;
  path: string;
  title: string;
  topics: string[];
  updated_at: string;
  inbound_links: number;
  confidence: number;
  // ADR-064: Filter fields
  created_at?: string;
  source_count: number;
  has_synthesis: boolean;
  synthesis_model?: string;
  average_rating?: number;
  rating_count: number;
}

// ADR-064: Filter facets
interface WikiFilterFacets {
  source_count: Record<string, number>;
  rating: Record<string, number>;
  synthesis_model: Record<string, number>;
  has_synthesis: Record<string, number>;
}

// ADR-064: Wiki pages response with facets
interface WikiPagesResponse {
  total: number;
  filtered: number;
  pages: WikiPageSummary[];
  facets?: WikiFilterFacets;
}

// ADR-064: Filter state
interface WikiFilters {
  min_sources?: number;
  max_sources?: number;
  has_synthesis?: boolean;
  synthesis_model?: string;
  min_rating?: number;
  sort_by?: string;
  sort_order?: string;
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

interface WikiChange {
  page_path: string;
  page_title: string;
  operation: string;
  changed_at: string;
  source_id?: string;
  agent_id?: string;
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
async function fetchRecentChanges(guildId: string): Promise<WikiChange[]> {
  const result = await api.get<{ changes: WikiChange[] }>(`/guilds/${guildId}/wiki/recent`);
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

// ADR-064: Fetch filtered pages with facets
async function fetchWikiPages(
  guildId: string,
  filters: WikiFilters = {},
  includeFacets: boolean = false
): Promise<WikiPagesResponse> {
  const params = new URLSearchParams();
  if (filters.min_sources !== undefined) params.append("min_sources", String(filters.min_sources));
  if (filters.max_sources !== undefined) params.append("max_sources", String(filters.max_sources));
  if (filters.has_synthesis !== undefined) params.append("has_synthesis", String(filters.has_synthesis));
  if (filters.synthesis_model) params.append("synthesis_model", filters.synthesis_model);
  if (filters.min_rating !== undefined) params.append("min_rating", String(filters.min_rating));
  if (filters.sort_by) params.append("sort_by", filters.sort_by);
  if (filters.sort_order) params.append("sort_order", filters.sort_order);
  if (includeFacets) params.append("include_facets", "true");
  params.append("limit", "50");

  return api.get<WikiPagesResponse>(`/guilds/${guildId}/wiki/pages?${params.toString()}`);
}

// ADR-065: Rate synthesis
interface RateSynthesisResult {
  success: boolean;
  average_rating: number | null;
  rating_count: number;
}

async function rateSynthesis(
  guildId: string,
  path: string,
  rating: number,
  feedback?: string
): Promise<RateSynthesisResult> {
  return api.post<RateSynthesisResult>(`/guilds/${guildId}/wiki/pages/${path}/rate`, {
    rating,
    feedback,
  });
}

// ADR-065: Synthesize with options
interface SynthesizeOptions {
  model?: string;
  temperature?: number;
  max_tokens?: number;
  focus_areas?: string[];
  custom_instructions?: string;
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

// ADR-068: Wiki Backfill Jobs
interface BackfillRequest {
  mode: "unprocessed" | "all" | "date_range";
  batch_size?: number;
  delay_between_batches?: number;
  date_from?: string;
  date_to?: string;
}

interface BackfillJobResponse {
  job_id: string;
  status: string;
  total_summaries: number;
  message: string;
}

interface BackfillStatus {
  job_id: string;
  status: string;
  progress_current: number;
  progress_total: number;
  progress_message: string;
  stats: {
    ingested: number;
    skipped: number;
    failed: number;
  };
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

async function startBackfill(guildId: string, request: BackfillRequest): Promise<BackfillJobResponse> {
  return api.post<BackfillJobResponse>(`/guilds/${guildId}/wiki/backfill`, request);
}

async function getBackfillStatus(guildId: string): Promise<BackfillStatus | null> {
  try {
    return await api.get<BackfillStatus>(`/guilds/${guildId}/wiki/backfill/status`);
  } catch {
    return null;
  }
}

async function cancelBackfill(guildId: string): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>(`/guilds/${guildId}/wiki/backfill/cancel`, {});
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

// Synthesize wiki page (ADR-065: with options support)
async function synthesizeWikiPage(
  guildId: string,
  path: string,
  options?: SynthesizeOptions
): Promise<{ success: boolean; model_used?: string }> {
  return api.post<{ success: boolean; model_used?: string }>(
    `/guilds/${guildId}/wiki/pages/${path}/synthesize`,
    options || {}
  );
}

// ADR-065: Star Rating component
function StarRating({
  rating,
  onRate,
  readonly = false,
  size = "default",
}: {
  rating: number;
  onRate?: (rating: number) => void;
  readonly?: boolean;
  size?: "default" | "small";
}) {
  const [hoverRating, setHoverRating] = useState(0);
  const starSize = size === "small" ? "h-3 w-3" : "h-5 w-5";

  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => {
        const filled = hoverRating ? star <= hoverRating : star <= rating;
        return (
          <button
            key={star}
            type="button"
            disabled={readonly}
            className={`${readonly ? "cursor-default" : "cursor-pointer hover:scale-110"} transition-transform`}
            onMouseEnter={() => !readonly && setHoverRating(star)}
            onMouseLeave={() => !readonly && setHoverRating(0)}
            onClick={() => onRate?.(star)}
          >
            <Star
              className={`${starSize} ${
                filled
                  ? "fill-yellow-400 text-yellow-400"
                  : "fill-transparent text-muted-foreground"
              }`}
            />
          </button>
        );
      })}
    </div>
  );
}

function WikiPageView({ page }: { page: WikiPage }) {
  const { id: guildId } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);
  const { toast } = useToast();

  // URL-based tab selection (ADR-063): ?tab=synthesis or ?tab=updates
  const tabFromUrl = searchParams.get("tab") as "synthesis" | "updates" | null;
  const defaultTab = page.synthesis ? "synthesis" : "updates";
  const activeTab = tabFromUrl && ["synthesis", "updates"].includes(tabFromUrl) ? tabFromUrl : defaultTab;

  const setActiveTab = (tab: "synthesis" | "updates") => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set("tab", tab);
    setSearchParams(newParams, { replace: true });
  };

  // Parse path for breadcrumb
  const pathParts = page.path.split("/");
  const category = pathParts[0];

  // Build source ID to title map
  const sourceMap = new Map(
    page.source_metadata?.map((s) => [s.id, s.title]) || []
  );

  // Format source title for display (truncate long titles)
  const formatSourceTitle = (sourceId: string) => {
    const title = sourceMap.get(sourceId);
    if (!title) return sourceId;
    // Extract key info: "Summary: #welcome, +41 more — Apr 04, 11:12" -> "Server Summary (44 channels) — Apr 04, 11:12"
    const match = title.match(/Summary:\s*(.+?)\s*—\s*(.+?)(?:\s*-\s*\d{4}-\d{2}-\d{2})?$/);
    if (match) {
      const channels = match[1];
      const timestamp = match[2];
      // Count channels mentioned
      const plusMore = channels.match(/\+(\d+)\s*more/);
      const explicitChannels = (channels.match(/#\w+/g) || []).length;
      const totalChannels = plusMore ? explicitChannels + parseInt(plusMore[1]) : explicitChannels;
      return totalChannels > 0
        ? `Server Summary (${totalChannels} channel${totalChannels > 1 ? 's' : ''}) — ${timestamp}`
        : `Summary — ${timestamp}`;
    }
    return title.length > 60 ? title.substring(0, 57) + '...' : title;
  };

  // Pre-process content to convert [source:summary-xxx] to links
  // Replace "## Update from summary-xxx" with readable titles
  let processedContent = page.content
    .replace(/\[source:(summary-[\w-]+)\]/g, '[📄 source](?source=$1)');

  // Replace "## Update from summary-xxx" with readable source titles
  processedContent = processedContent.replace(
    /## Update from (summary-[\w-]+)/g,
    (_, sourceId) => `## 📝 ${formatSourceTitle(sourceId)} [↗](?source=${sourceId})`
  );

  // Regenerate synthesis mutation
  const synthesizeMutation = useMutation({
    mutationFn: (options?: SynthesizeOptions) => synthesizeWikiPage(guildId!, page.path, options),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["wiki-page", guildId, page.path] });
      toast({ title: "Synthesis regenerated" });
    },
    onError: () => {
      toast({ title: "Failed to generate synthesis", variant: "destructive" });
    },
  });

  // ADR-065: Rating mutation
  const ratingMutation = useMutation({
    mutationFn: (rating: number) => rateSynthesis(guildId!, page.path, rating),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["wiki-page", guildId, page.path] });
      toast({
        title: "Rating submitted",
        description: `Average rating: ${data.average_rating?.toFixed(1)} (${data.rating_count} ratings)`,
      });
    },
    onError: () => {
      toast({ title: "Failed to submit rating", variant: "destructive" });
    },
  });

  // Copy page URL to clipboard (includes current tab)
  const handleShare = async () => {
    // Build URL with current tab parameter
    const url = new URL(window.location.href);
    url.searchParams.set("tab", activeTab);
    const shareUrl = url.toString();

    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      toast({
        title: "Link copied!",
        description: `Wiki page URL copied (${activeTab} view)`,
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
                {/* ADR-065: Synthesis footer with rating and metadata */}
                <div className="mt-4 pt-4 border-t flex items-center justify-between flex-wrap gap-4">
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    {/* Model */}
                    {page.synthesis_model && (
                      <span className="flex items-center gap-1">
                        <Cpu className="h-3 w-3" />
                        {page.synthesis_model.replace("anthropic/", "")}
                      </span>
                    )}
                    {/* Timestamp */}
                    {page.synthesis_updated_at && (
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {new Date(page.synthesis_updated_at).toLocaleDateString()}
                      </span>
                    )}
                    {/* Sources */}
                    <span className="flex items-center gap-1">
                      <FileText className="h-3 w-3" />
                      {page.synthesis_source_count} sources
                    </span>
                  </div>
                  <div className="flex items-center gap-4">
                    {/* Current rating */}
                    {page.rating_count > 0 && (
                      <span className="flex items-center gap-1 text-sm">
                        <StarRating rating={page.average_rating || 0} readonly size="small" />
                        <span className="text-muted-foreground">
                          {page.average_rating?.toFixed(1)} ({page.rating_count})
                        </span>
                      </span>
                    )}
                    {/* Rate button */}
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">Rate:</span>
                      <StarRating
                        rating={0}
                        onRate={(r) => ratingMutation.mutate(r)}
                      />
                    </div>
                  </div>
                </div>
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
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Card className="cursor-help">
                <CardContent className="pt-4">
                  <div className="text-sm text-muted-foreground">Links</div>
                  <div className="text-2xl font-bold">
                    {page.inbound_links + page.outbound_links}
                  </div>
                </CardContent>
              </Card>
            </TooltipTrigger>
            <TooltipContent>
              <p>{page.inbound_links} inbound · {page.outbound_links} outbound</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
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

      {/* Related Pages */}
      {(page.linked_pages_from?.length > 0 || page.linked_pages_to?.length > 0) && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Link2 className="h-4 w-4" />
              Related Pages
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {page.linked_pages_from?.length > 0 && (
              <div>
                <div className="text-sm text-muted-foreground mb-2">Links to:</div>
                <div className="flex flex-wrap gap-2">
                  {page.linked_pages_from.map((link) => (
                    <Link
                      key={link.path}
                      to={`/guilds/${guildId}/wiki/${link.path}`}
                      className="text-sm text-primary hover:underline flex items-center gap-1"
                    >
                      <FileText className="h-3 w-3" />
                      {link.title}
                    </Link>
                  ))}
                </div>
              </div>
            )}
            {page.linked_pages_to?.length > 0 && (
              <div>
                <div className="text-sm text-muted-foreground mb-2">Linked from:</div>
                <div className="flex flex-wrap gap-2">
                  {page.linked_pages_to.map((link) => (
                    <Link
                      key={link.path}
                      to={`/guilds/${guildId}/wiki/${link.path}`}
                      className="text-sm text-primary hover:underline flex items-center gap-1"
                    >
                      <FileText className="h-3 w-3" />
                      {link.title}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
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
      {changes?.map((change, index) => (
        <Link
          key={`${change.page_path}-${index}`}
          to={`/guilds/${guildId}/wiki/${change.page_path}`}
          className="block"
        >
          <Card className="hover:bg-accent/50 transition-colors">
            <CardContent className="py-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium">{change.page_title}</span>
                  <span className="text-sm text-muted-foreground ml-2">
                    {change.changed_at
                      ? new Date(change.changed_at).toLocaleDateString()
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

// ADR-064: Wiki Browser with filters
function WikiBrowser({ guildId }: { guildId: string }) {
  const [filters, setFilters] = useState<WikiFilters>({
    sort_by: "updated_at",
    sort_order: "desc",
  });
  const [showFilters, setShowFilters] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["wiki-pages", guildId, filters],
    queryFn: () => fetchWikiPages(guildId, filters, true),
  });

  const clearFilters = () => {
    setFilters({ sort_by: "updated_at", sort_order: "desc" });
  };

  const hasActiveFilters = filters.min_sources !== undefined ||
    filters.has_synthesis !== undefined ||
    filters.synthesis_model !== undefined ||
    filters.min_rating !== undefined;

  return (
    <div className="space-y-4">
      {/* Filter toggle */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowFilters(!showFilters)}
          className={hasActiveFilters ? "border-primary" : ""}
        >
          <SlidersHorizontal className="h-4 w-4 mr-2" />
          Filters
          {hasActiveFilters && (
            <Badge variant="secondary" className="ml-2">Active</Badge>
          )}
        </Button>
        <div className="text-sm text-muted-foreground">
          {data?.filtered || 0} of {data?.total || 0} pages
        </div>
      </div>

      {/* Filter panel */}
      {showFilters && (
        <Card>
          <CardContent className="pt-4 space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {/* Source count filter */}
              <div>
                <label className="text-sm font-medium mb-2 block">Sources</label>
                <div className="flex flex-wrap gap-1">
                  {["1", "2-5", "5-10", "10+"].map((bucket) => {
                    const [min, max] = bucket === "1" ? [1, 1] :
                      bucket === "2-5" ? [2, 5] :
                      bucket === "5-10" ? [5, 10] : [10, undefined];
                    const isActive = filters.min_sources === min;
                    return (
                      <Badge
                        key={bucket}
                        variant={isActive ? "default" : "outline"}
                        className="cursor-pointer"
                        onClick={() => setFilters(f => ({
                          ...f,
                          min_sources: isActive ? undefined : min,
                          max_sources: isActive ? undefined : max,
                        }))}
                      >
                        {bucket}
                        {data?.facets?.source_count[bucket] !== undefined && (
                          <span className="ml-1 opacity-60">
                            ({data.facets.source_count[bucket]})
                          </span>
                        )}
                      </Badge>
                    );
                  })}
                </div>
              </div>

              {/* Synthesis filter */}
              <div>
                <label className="text-sm font-medium mb-2 block">Synthesis</label>
                <div className="flex gap-1">
                  <Badge
                    variant={filters.has_synthesis === true ? "default" : "outline"}
                    className="cursor-pointer"
                    onClick={() => setFilters(f => ({
                      ...f,
                      has_synthesis: f.has_synthesis === true ? undefined : true,
                    }))}
                  >
                    <Sparkles className="h-3 w-3 mr-1" />
                    With synthesis
                    {data?.facets?.has_synthesis["true"] !== undefined && (
                      <span className="ml-1 opacity-60">
                        ({data.facets.has_synthesis["true"]})
                      </span>
                    )}
                  </Badge>
                </div>
              </div>

              {/* Rating filter */}
              <div>
                <label className="text-sm font-medium mb-2 block">Min Rating</label>
                <div className="flex gap-1">
                  {[3, 4, 5].map((rating) => (
                    <Badge
                      key={rating}
                      variant={filters.min_rating === rating ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => setFilters(f => ({
                        ...f,
                        min_rating: f.min_rating === rating ? undefined : rating,
                      }))}
                    >
                      {rating}+ ★
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Sort */}
              <div>
                <label className="text-sm font-medium mb-2 block">Sort By</label>
                <select
                  className="w-full rounded-md border bg-background px-3 py-1 text-sm"
                  value={filters.sort_by}
                  onChange={(e) => setFilters(f => ({ ...f, sort_by: e.target.value }))}
                >
                  <option value="updated_at">Recently Updated</option>
                  <option value="created_at">Recently Created</option>
                  <option value="source_count">Most Sources</option>
                  <option value="rating">Highest Rated</option>
                  <option value="title">Title (A-Z)</option>
                </select>
              </div>
            </div>

            {/* Clear filters */}
            {hasActiveFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="h-4 w-4 mr-1" />
                Clear filters
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : (
        <div className="space-y-2">
          {data?.pages.map((page) => (
            <Link
              key={page.id}
              to={`/guilds/${guildId}/wiki/${page.path}`}
              className="block"
            >
              <Card className="hover:bg-accent/50 transition-colors">
                <CardContent className="py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium truncate">{page.title}</span>
                        {page.has_synthesis && (
                          <Sparkles className="h-3 w-3 text-yellow-500 flex-shrink-0" />
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-sm text-muted-foreground mt-1">
                        <span>{page.source_count} sources</span>
                        {page.average_rating && (
                          <span className="flex items-center gap-1">
                            <Star className="h-3 w-3 fill-yellow-400 text-yellow-400" />
                            {page.average_rating.toFixed(1)}
                          </span>
                        )}
                        <span>{page.path}</span>
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
          {(!data?.pages || data.pages.length === 0) && (
            <Card>
              <CardContent className="py-8 text-center">
                <p className="text-muted-foreground">No pages match your filters</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

function PopulateWiki({ guildId }: { guildId: string }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [backfillMode, setBackfillMode] = useState<"unprocessed" | "all">("unprocessed");

  // Fetch stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["wiki-stats", guildId],
    queryFn: () => fetchWikiStats(guildId),
  });

  // ADR-068: Fetch backfill status (poll every 3s when active)
  const { data: backfillStatus, refetch: refetchBackfill } = useQuery({
    queryKey: ["wiki-backfill-status", guildId],
    queryFn: () => getBackfillStatus(guildId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "pending" ? 3000 : false;
    },
  });

  const isBackfillActive = backfillStatus?.status === "running" || backfillStatus?.status === "pending";

  // ADR-068: Start backfill mutation
  const startBackfillMutation = useMutation({
    mutationFn: (mode: "unprocessed" | "all") => startBackfill(guildId, {
      mode,
      batch_size: 10,
      delay_between_batches: 1.0,
    }),
    onSuccess: (data) => {
      refetchBackfill();
      toast({
        title: "Backfill started",
        description: data.message,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to start backfill",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // ADR-068: Cancel backfill mutation
  const cancelBackfillMutation = useMutation({
    mutationFn: () => cancelBackfill(guildId),
    onSuccess: () => {
      refetchBackfill();
      queryClient.invalidateQueries({ queryKey: ["wiki-stats", guildId] });
      toast({ title: "Backfill cancelled" });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to cancel backfill",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Populate mutation (legacy sync)
  const populateMutation = useMutation({
    mutationFn: (days: number) => populateWiki(guildId, days),
    onSuccess: () => {
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

  // Calculate backfill progress percentage
  const backfillPercent = backfillStatus?.progress_total
    ? Math.round((backfillStatus.progress_current / backfillStatus.progress_total) * 100)
    : 0;

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

      {/* ADR-068: Backfill Card */}
      <Card className="border-primary/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Backfill Wiki from Summaries
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Process existing summaries that haven't been ingested into the wiki yet.
            This runs as a background job with progress tracking.
          </p>

          {/* Active backfill status */}
          {isBackfillActive && backfillStatus && (
            <div className="space-y-3 p-4 bg-muted rounded-lg">
              <div className="flex items-center justify-between">
                <span className="font-medium flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Backfill in progress
                </span>
                <Badge variant="secondary">{backfillPercent}%</Badge>
              </div>
              <div className="w-full bg-background rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all"
                  style={{ width: `${backfillPercent}%` }}
                />
              </div>
              <div className="text-sm text-muted-foreground">
                {backfillStatus.progress_message || `${backfillStatus.progress_current} / ${backfillStatus.progress_total} summaries`}
              </div>
              {backfillStatus.stats && (
                <div className="flex gap-4 text-xs">
                  <span className="text-green-600">✓ {backfillStatus.stats.ingested} ingested</span>
                  <span className="text-yellow-600">○ {backfillStatus.stats.skipped} skipped</span>
                  <span className="text-red-600">✕ {backfillStatus.stats.failed} failed</span>
                </div>
              )}
              <Button
                variant="destructive"
                size="sm"
                onClick={() => cancelBackfillMutation.mutate()}
                disabled={cancelBackfillMutation.isPending}
              >
                <Square className="h-3 w-3 mr-1" />
                Cancel
              </Button>
            </div>
          )}

          {/* Completed backfill status */}
          {backfillStatus?.status === "completed" && (
            <Alert>
              <Sparkles className="h-4 w-4" />
              <AlertTitle>Backfill Complete</AlertTitle>
              <AlertDescription>
                Processed {backfillStatus.progress_total} summaries.
                {backfillStatus.stats && (
                  <span>
                    {" "}{backfillStatus.stats.ingested} ingested, {backfillStatus.stats.failed} failed.
                  </span>
                )}
              </AlertDescription>
            </Alert>
          )}

          {/* Start backfill controls */}
          {!isBackfillActive && (
            <div className="space-y-3">
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="backfillMode"
                    checked={backfillMode === "unprocessed"}
                    onChange={() => setBackfillMode("unprocessed")}
                    className="w-4 h-4"
                  />
                  <span className="text-sm">Only un-processed summaries</span>
                  <Badge variant="secondary">Recommended</Badge>
                </label>
              </div>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="backfillMode"
                    checked={backfillMode === "all"}
                    onChange={() => setBackfillMode("all")}
                    className="w-4 h-4"
                  />
                  <span className="text-sm">All summaries (full rebuild)</span>
                </label>
              </div>
              <Button
                onClick={() => startBackfillMutation.mutate(backfillMode)}
                disabled={startBackfillMutation.isPending}
              >
                {startBackfillMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Start Backfill
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick Populate Card (legacy sync) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings2 className="h-5 w-5" />
            Quick Populate (Sync)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Quick sync populate from recent summaries. Use for small batches;
            for large datasets use the backfill job above.
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
              variant="outline"
              onClick={() => populateMutation.mutate(30)}
              disabled={populateMutation.isPending || isBackfillActive}
            >
              {populateMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Last 30 Days
            </Button>
            <Button
              variant="outline"
              onClick={() => populateMutation.mutate(90)}
              disabled={populateMutation.isPending || isBackfillActive}
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
              disabled={clearMutation.isPending || !stats?.total_pages || isBackfillActive}
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
                <WikiBrowser guildId={guildId!} />
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
