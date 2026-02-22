import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import { useGenerateSummary, useTaskStatus } from "@/hooks/useSummaries";
import { useGuild } from "@/hooks/useGuilds";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
import { Checkbox } from "@/components/ui/checkbox";
import { Sparkles, FileText, Loader2, Hash, FolderOpen, Server, Search, Archive as ArchiveIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { StoredSummariesTab } from "@/components/summaries/StoredSummariesTab";
import type { SummaryOptions, GenerateRequest } from "@/types";

export function Summaries() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const { data: guild } = useGuild(id || "");
  const generateSummary = useGenerateSummary(id || "");
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // ADR-009, ADR-012: Read source and highlight from URL params
  const sourceParam = searchParams.get("source");
  const highlightParam = searchParams.get("highlight");

  // ADR-012: Default to "all" (All Summaries) tab - unified view
  const [activeTab, setActiveTab] = useState("all");

  const [generateOpen, setGenerateOpen] = useState(false);
  const [scope, setScope] = useState<"channel" | "category" | "guild">("channel");
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [timeRange, setTimeRange] = useState("24h");
  const [summaryLength, setSummaryLength] = useState<SummaryOptions["summary_length"]>("detailed");
  const [perspective, setPerspective] = useState<SummaryOptions["perspective"]>("general");
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [channelSearch, setChannelSearch] = useState("");

  // Poll task status when generating
  const taskStatus = useTaskStatus(id || "", activeTaskId);
  const [taskStartTime, setTaskStartTime] = useState<number | null>(null);

  // Track when task starts
  useEffect(() => {
    if (activeTaskId && !taskStartTime) {
      setTaskStartTime(Date.now());
    } else if (!activeTaskId) {
      setTaskStartTime(null);
    }
  }, [activeTaskId, taskStartTime]);

  // Handle task completion
  useEffect(() => {
    if (!taskStatus.data) return;

    if (taskStatus.data.status === "completed") {
      // ADR-012: Invalidate stored summaries since Generate now saves there
      queryClient.invalidateQueries({ queryKey: ["stored-summaries", id] });
      setActiveTaskId(null);
      toast({
        title: "Summary ready!",
        description: "Your summary has been generated successfully.",
      });
    } else if (taskStatus.data.status === "failed") {
      setActiveTaskId(null);
      toast({
        title: "Generation failed",
        description: taskStatus.data.error || "Failed to generate summary.",
        variant: "destructive",
      });
    }
  }, [taskStatus.data?.status, id, queryClient, toast]);

  // Timeout mechanism - fail after 5 minutes
  useEffect(() => {
    if (!activeTaskId || !taskStartTime) return;

    const timeout = setTimeout(() => {
      if (activeTaskId && taskStatus.data?.status === "processing") {
        setActiveTaskId(null);
        toast({
          title: "Generation timed out",
          description: "The summary generation is taking too long. Please try again or check the Jobs tab.",
          variant: "destructive",
        });
      }
    }, 5 * 60 * 1000); // 5 minutes

    return () => clearTimeout(timeout);
  }, [activeTaskId, taskStartTime, taskStatus.data?.status, toast]);

  // Show error if task status fetch fails
  useEffect(() => {
    if (taskStatus.isError && activeTaskId) {
      toast({
        title: "Connection error",
        description: "Failed to check generation status. The task may still be running.",
        variant: "destructive",
      });
    }
  }, [taskStatus.isError, activeTaskId, toast]);

  const handleGenerate = async () => {
    try {
      const timeValue = parseInt(timeRange.replace(/\D/g, ""));
      const timeType = timeRange.includes("d") ? "days" : "hours";
      
      const request: GenerateRequest = {
        scope,
        time_range: {
          type: timeType as "hours" | "days",
          value: timeValue,
        },
        options: {
          summary_length: summaryLength,
          include_action_items: true,
          include_technical_terms: true,
        },
      };

      // Add scope-specific fields
      if (scope === "channel") {
        request.channel_ids = selectedChannels.length > 0 ? selectedChannels : guild?.config.enabled_channels || [];
      } else if (scope === "category") {
        request.category_id = selectedCategory;
      }
      // For "guild" scope, no additional fields needed
      
      const result = await generateSummary.mutateAsync(request);
      
      // Store task ID for polling
      setActiveTaskId(result.task_id);
      
      setGenerateOpen(false);
      toast({
        title: "Summary generation started",
        description: "Your summary is being generated...",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to start summary generation.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold">Summaries</h1>
          <p className="text-muted-foreground">
            View past summaries and generate new ones
          </p>
        </div>
        <Dialog open={generateOpen} onOpenChange={setGenerateOpen}>
          <DialogTrigger asChild>
            <Button>
              <Sparkles className="mr-2 h-4 w-4" />
              Generate Summary
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Generate Summary</DialogTitle>
              <DialogDescription>
                Configure your summary options
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              {/* Scope Selector */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Scope</label>
                <div className="grid grid-cols-3 gap-2">
                  <Button
                    type="button"
                    variant={scope === "channel" ? "default" : "outline"}
                    size="sm"
                    className="w-full"
                    onClick={() => setScope("channel")}
                  >
                    <Hash className="mr-1.5 h-3.5 w-3.5" />
                    Channel
                  </Button>
                  <Button
                    type="button"
                    variant={scope === "category" ? "default" : "outline"}
                    size="sm"
                    className="w-full"
                    onClick={() => setScope("category")}
                  >
                    <FolderOpen className="mr-1.5 h-3.5 w-3.5" />
                    Category
                  </Button>
                  <Button
                    type="button"
                    variant={scope === "guild" ? "default" : "outline"}
                    size="sm"
                    className="w-full"
                    onClick={() => setScope("guild")}
                  >
                    <Server className="mr-1.5 h-3.5 w-3.5" />
                    Server
                  </Button>
                </div>
              </div>

              {/* Channel Selection - only shown when scope is "channel" */}
              {scope === "channel" && guild?.channels && (
                <div className="space-y-2">
                  <label className="text-sm font-medium">Channels</label>
                  <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search channels..."
                      value={channelSearch}
                      onChange={(e) => setChannelSearch(e.target.value)}
                      className="pl-8"
                    />
                  </div>
                  <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">
                    {guild.channels
                      .filter(c => c.type === "text")
                      .filter(c => c.name.toLowerCase().includes(channelSearch.toLowerCase()))
                      .map((channel) => (
                        <div key={channel.id} className="flex items-center space-x-2">
                          <Checkbox
                            id={channel.id}
                            checked={selectedChannels.includes(channel.id)}
                            onCheckedChange={(checked) => {
                              if (checked) {
                                setSelectedChannels([...selectedChannels, channel.id]);
                              } else {
                                setSelectedChannels(selectedChannels.filter(id => id !== channel.id));
                              }
                            }}
                          />
                          <label htmlFor={channel.id} className="text-sm cursor-pointer">
                            #{channel.name}
                          </label>
                        </div>
                      ))}
                    {guild.channels
                      .filter(c => c.type === "text")
                      .filter(c => c.name.toLowerCase().includes(channelSearch.toLowerCase()))
                      .length === 0 && (
                      <p className="text-sm text-muted-foreground py-2 text-center">
                        No channels match "{channelSearch}"
                      </p>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {selectedChannels.length === 0 
                      ? "All enabled channels will be included" 
                      : `${selectedChannels.length} channel(s) selected`}
                  </p>
                </div>
              )}

              {/* Category Selection - only shown when scope is "category" */}
              {scope === "category" && guild?.categories && (
                <div className="space-y-2">
                  <label className="text-sm font-medium">Category</label>
                  <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select a category" />
                    </SelectTrigger>
                    <SelectContent>
                      {guild.categories.map((category) => (
                        <SelectItem key={category.id} value={category.id}>
                          {category.name} ({category.channel_count} channels)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Guild scope info */}
              {scope === "guild" && (
                <div className="rounded-md border border-primary/20 bg-primary/5 p-3">
                  <p className="text-sm text-muted-foreground">
                    All enabled channels across the server will be summarized.
                  </p>
                </div>
              )}

              <div className="space-y-2">
                <label className="text-sm font-medium">Time Range</label>
                <Select value={timeRange} onValueChange={setTimeRange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select time range" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1h">Last 1 hour</SelectItem>
                    <SelectItem value="6h">Last 6 hours</SelectItem>
                    <SelectItem value="12h">Last 12 hours</SelectItem>
                    <SelectItem value="24h">Last 24 hours</SelectItem>
                    <SelectItem value="48h">Last 48 hours</SelectItem>
                    <SelectItem value="7d">Last 7 days</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Summary Length</label>
                <Select value={summaryLength} onValueChange={(v) => setSummaryLength(v as SummaryOptions["summary_length"])}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="brief">Brief</SelectItem>
                    <SelectItem value="detailed">Detailed</SelectItem>
                    <SelectItem value="comprehensive">Comprehensive</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Perspective</label>
                <Select value={perspective} onValueChange={(v) => setPerspective(v as SummaryOptions["perspective"])}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">General</SelectItem>
                    <SelectItem value="developer">Developer</SelectItem>
                    <SelectItem value="marketing">Marketing</SelectItem>
                    <SelectItem value="executive">Executive</SelectItem>
                    <SelectItem value="support">Support</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button 
                className="w-full" 
                onClick={handleGenerate}
                disabled={generateSummary.isPending}
              >
                {generateSummary.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Generate
                  </>
                )}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </motion.div>

      {/* Generation Progress */}
      {activeTaskId && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <Card className="border-primary/50 bg-primary/5">
            <CardContent className="flex items-center gap-3 p-4">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <div>
                <p className="font-medium">Generating summary...</p>
                <p className="text-sm text-muted-foreground">This may take a moment</p>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* ADR-012: Consolidated Tabs - All Summaries + Retrospective Jobs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="all" className="gap-2">
            <FileText className="h-4 w-4" />
            All Summaries
          </TabsTrigger>
          <TabsTrigger value="retrospective" className="gap-2">
            <ArchiveIcon className="h-4 w-4" />
            Retrospective Jobs
          </TabsTrigger>
        </TabsList>

        {/* All Summaries Tab - Unified view (ADR-012) */}
        <TabsContent value="all">
          <StoredSummariesTab guildId={id || ""} initialSource={sourceParam as "archive" | "scheduled" | "manual" | undefined} />
        </TabsContent>

        {/* Retrospective Jobs Tab - Archive job management */}
        <TabsContent value="retrospective">
          <RetrospectiveJobsInfo guildId={id || ""} />
        </TabsContent>
      </Tabs>
    </div>
  );
}


/**
 * ADR-012: Retrospective Jobs Info
 *
 * This tab provides information about retrospective job management
 * and links to the Archive page for generating retrospective summaries.
 */
function RetrospectiveJobsInfo({ guildId }: { guildId: string }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6"
    >
      <div className="rounded-md border border-primary/20 bg-primary/5 p-4">
        <h3 className="font-medium mb-2 flex items-center gap-2">
          <ArchiveIcon className="h-4 w-4" />
          About Retrospective Summaries
        </h3>
        <p className="text-sm text-muted-foreground mb-4">
          Retrospective summaries are generated from historical Discord data.
          They appear in the <strong>All Summaries</strong> tab with an "Archive" badge
          and can be pushed to any channel like regular summaries.
        </p>
        <div className="flex gap-2">
          <Button asChild>
            <a href={`/guilds/${guildId}/archive`}>
              <ArchiveIcon className="mr-2 h-4 w-4" />
              Generate Retrospective Summaries
            </a>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">How It Works</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <div className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-medium">1</span>
            <p>Go to the <strong>Retrospective</strong> page to select date ranges and channels for historical analysis.</p>
          </div>
          <div className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-medium">2</span>
            <p>Generate summaries for past dates - they'll be stored in the database automatically.</p>
          </div>
          <div className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-medium">3</span>
            <p>View all generated summaries in the <strong>All Summaries</strong> tab - filter by "Archive" source to see only retrospective summaries.</p>
          </div>
          <div className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-medium">4</span>
            <p>Push any summary to Discord channels using the "Push to Channel" button.</p>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

