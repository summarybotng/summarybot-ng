import { useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
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
  content: string;
  topics: string[];
  source_refs: string[];
  inbound_links: number;
  outbound_links: number;
  confidence: number;
  created_at: string;
  updated_at: string;
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
  const response = await api.get(`/guilds/${guildId}/wiki/tree`);
  return response.data;
}

// Fetch wiki page
async function fetchWikiPage(guildId: string, path: string): Promise<WikiPage> {
  const response = await api.get(`/guilds/${guildId}/wiki/pages/${path}`);
  return response.data;
}

// Search wiki
async function searchWiki(guildId: string, query: string): Promise<WikiSearchResult> {
  const response = await api.get(`/guilds/${guildId}/wiki/search`, {
    params: { q: query, synthesize: true },
  });
  return response.data;
}

// Fetch recent changes
async function fetchRecentChanges(guildId: string): Promise<WikiPageSummary[]> {
  const response = await api.get(`/guilds/${guildId}/wiki/recent`);
  return response.data;
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

function WikiPageView({ page }: { page: WikiPage }) {
  const { id: guildId } = useParams<{ id: string }>();

  // Parse path for breadcrumb
  const pathParts = page.path.split("/");
  const category = pathParts[0];

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
            <BreadcrumbLink className="capitalize">{category}</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{page.title}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Title */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{page.title}</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            Suggest Edit
          </Button>
          <Button variant="outline" size="sm">
            <ExternalLink className="h-4 w-4 mr-1" />
            Share
          </Button>
        </div>
      </div>

      {/* Content */}
      <Card>
        <CardContent className="pt-6">
          <article className="prose dark:prose-invert max-w-none">
            {/* Simple markdown rendering - in production use react-markdown */}
            <div className="whitespace-pre-wrap">{page.content}</div>
          </article>
        </CardContent>
      </Card>

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

export function Wiki() {
  const { id: guildId, "*": pagePath } = useParams<{ id: string; "*": string }>();
  const [searchParams] = useSearchParams();
  const searchQuery = searchParams.get("q");

  // Fetch tree
  const { data: tree, isLoading: treeLoading } = useQuery({
    queryKey: ["wiki-tree", guildId],
    queryFn: () => fetchWikiTree(guildId!),
    enabled: !!guildId,
  });

  // Fetch page if path is provided
  const { data: page, isLoading: pageLoading } = useQuery({
    queryKey: ["wiki-page", guildId, pagePath],
    queryFn: () => fetchWikiPage(guildId!, pagePath!),
    enabled: !!guildId && !!pagePath,
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
          {searchQuery ? (
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
            </Tabs>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default Wiki;
