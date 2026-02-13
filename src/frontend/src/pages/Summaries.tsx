import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import { useSummaries, useSummary, useGenerateSummary, useTaskStatus, usePushSummary } from "@/hooks/useSummaries";
import { useGuild } from "@/hooks/useGuilds";
import { useTimezone } from "@/contexts/TimezoneContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
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
import { Sparkles, FileText, Calendar, MessageSquare, Clock, Users, Loader2, AlertCircle, RefreshCw, Hash, FolderOpen, Server, Eye, Search, Send, Archive, Link } from "lucide-react";
import { Input } from "@/components/ui/input";
import { SummaryPromptDialog } from "@/components/summaries/SummaryPromptDialog";
import { StoredSummariesTab } from "@/components/summaries/StoredSummariesTab";
import { PushToChannelModal } from "@/components/summaries/PushToChannelModal";
import type { Summary, SummaryOptions, GenerateRequest, Channel, PushToChannelRequest } from "@/types";

export function Summaries() {
  const { id } = useParams<{ id: string }>();
  const { data: summariesData, isLoading, isError, error, refetch } = useSummaries(id || "");
  const { data: guild } = useGuild(id || "");
  const generateSummary = useGenerateSummary(id || "");
  const { toast } = useToast();
  const queryClient = useQueryClient();
  
  const [selectedSummary, setSelectedSummary] = useState<string | null>(null);
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

  // Handle task completion
  useEffect(() => {
    if (!taskStatus.data) return;
    
    if (taskStatus.data.status === "completed") {
      queryClient.invalidateQueries({ queryKey: ["summaries", id] });
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

      {/* Tabs for History vs Stored */}
      <Tabs defaultValue="history" className="space-y-4">
        <TabsList>
          <TabsTrigger value="history" className="gap-2">
            <FileText className="h-4 w-4" />
            History
          </TabsTrigger>
          <TabsTrigger value="stored" className="gap-2">
            <Send className="h-4 w-4" />
            Stored & Share
          </TabsTrigger>
        </TabsList>

        {/* History Tab - Generated summaries */}
        <TabsContent value="history" className="space-y-4">
          {/* Error State */}
          {isError && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <Card className="border-destructive/50 bg-destructive/5">
                <CardContent className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-3">
                    <AlertCircle className="h-5 w-5 text-destructive" />
                    <div>
                      <p className="font-medium text-destructive">Failed to load summaries</p>
                      <p className="text-sm text-muted-foreground">
                        {error instanceof Error ? error.message : "An error occurred"}
                      </p>
                    </div>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => refetch()}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Retry
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {isLoading ? (
            <SummariesSkeleton />
          ) : summariesData?.summaries.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center py-20"
            >
              <FileText className="mb-4 h-16 w-16 text-muted-foreground/30" />
              <h2 className="mb-2 text-xl font-semibold">No summaries yet</h2>
              <p className="mb-6 text-center text-muted-foreground">
                Generate your first summary to get started
              </p>
              <Button onClick={() => setGenerateOpen(true)}>
                <Sparkles className="mr-2 h-4 w-4" />
                Generate Summary
              </Button>
            </motion.div>
          ) : (
            <div className="grid gap-4">
              {summariesData?.summaries.map((summary, index) => (
                <SummaryCard
                  key={summary.id}
                  summary={summary}
                  index={index}
                  onClick={() => setSelectedSummary(summary.id)}
                />
              ))}
            </div>
          )}
        </TabsContent>

        {/* Stored Tab - Summaries with Push to Channel */}
        <TabsContent value="stored">
          <div className="mb-4 rounded-md border border-primary/20 bg-primary/5 p-3">
            <p className="text-sm text-muted-foreground">
              <Send className="inline-block mr-1.5 h-4 w-4" />
              Stored summaries can be <strong>pushed to Discord channels</strong>. Create a schedule with "Dashboard" destination to store summaries here.
            </p>
          </div>
          <StoredSummariesTab guildId={id || ""} />
        </TabsContent>
      </Tabs>

      <SummaryDetailSheet
        guildId={id || ""}
        summaryId={selectedSummary}
        open={!!selectedSummary}
        onOpenChange={(open) => !open && setSelectedSummary(null)}
        channels={guild?.channels || []}
      />
    </div>
  );
}

function SummaryCard({ summary, index, onClick }: { summary: Summary; index: number; onClick: () => void }) {
  const { formatDate } = useTimezone();

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card
        className="cursor-pointer border-border/50 transition-all hover:border-primary/50 hover:shadow-lg"
        onClick={onClick}
      >
        <CardContent className="p-5">
          <div className="mb-3 flex items-start justify-between">
            <div className="flex items-center gap-2">
              <Badge variant="outline">#{summary.channel_name}</Badge>
              <Badge variant="secondary">{summary.summary_length}</Badge>
              {summary.has_prompt_data && (
                <Badge variant="outline" className="border-primary/50 text-primary">
                  <Eye className="mr-1 h-3 w-3" />
                  Details
                </Badge>
              )}
            </div>
            <span className="text-sm text-muted-foreground">
              {formatDate(summary.created_at)}
            </span>
          </div>

          <p className="mb-4 line-clamp-2 text-muted-foreground">
            {summary.preview}
          </p>

          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <Calendar className="h-4 w-4" />
              <span>
                {formatDate(summary.start_time)} - {formatDate(summary.end_time)}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <MessageSquare className="h-4 w-4" />
              <span>{summary.message_count} messages</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function SummaryDetailSheet({
  guildId,
  summaryId,
  open,
  onOpenChange,
  channels,
}: {
  guildId: string;
  summaryId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  channels: Channel[];
}) {
  const { data: summary, isLoading } = useSummary(guildId, summaryId || "");
  const [promptDialogOpen, setPromptDialogOpen] = useState(false);
  const [pushModalOpen, setPushModalOpen] = useState(false);
  const pushSummary = usePushSummary(guildId);
  const { toast } = useToast();
  const { formatDateTime, formatTime } = useTimezone();

  const handlePush = async (request: PushToChannelRequest) => {
    if (!summaryId) return;

    try {
      const result = await pushSummary.mutateAsync({
        summaryId,
        request,
      });

      setPushModalOpen(false);

      if (result.success) {
        toast({
          title: "Summary pushed!",
          description: `Successfully sent to ${result.successful_channels} of ${result.total_channels} channel(s).`,
        });
      } else {
        // Get error messages from failed deliveries
        const errors = result.deliveries
          ?.filter((d: { success: boolean; error?: string }) => !d.success && d.error)
          .map((d: { error?: string }) => d.error)
          .filter((e: string | undefined, i: number, arr: (string | undefined)[]) => arr.indexOf(e) === i); // unique

        toast({
          title: "Push failed",
          description: errors?.length ? errors.join(", ") : "Failed to send summary to any channels.",
          variant: "destructive",
        });
      }
    } catch {
      toast({
        title: "Error",
        description: "Failed to push summary to channels.",
        variant: "destructive",
      });
    }
  };

  return (
    <>
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
              <SheetTitle>#{summary.channel_name} Summary</SheetTitle>
              <SheetDescription>
                {formatDateTime(summary.start_time)} - {formatDateTime(summary.end_time)}
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
                  <span>{summary.participants.length} participants</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  <span>{summary.metadata.processing_time_ms}ms</span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => setPushModalOpen(true)}
                >
                  <Send className="mr-2 h-4 w-4" />
                  Push to Channel
                </Button>
                {summary.has_prompt_data && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPromptDialogOpen(true)}
                  >
                    <Eye className="mr-2 h-4 w-4" />
                    View Generation Details
                  </Button>
                )}
              </div>

              {/* Summary Text */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {summary.summary_text}
                  </p>
                </CardContent>
              </Card>

              {/* Key Points */}
              {summary.key_points.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Key Points</CardTitle>
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
              {summary.action_items.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Action Items</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-3">
                      {summary.action_items.map((item, i) => (
                        <li key={i} className="flex items-start gap-3">
                          <Badge variant={item.priority === "high" ? "destructive" : item.priority === "medium" ? "default" : "secondary"} className="mt-0.5">
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
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <Link className="h-4 w-4" />
                      References
                    </CardTitle>
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

              {/* Metadata */}
              {summary.metadata && (
                <div className="text-xs text-muted-foreground space-y-0.5">
                  {(summary.metadata.model_used || summary.metadata.model) ? (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span>Model: {summary.metadata.model_used || summary.metadata.model}</span>
                      {summary.metadata.model_requested && 
                       summary.metadata.model_requested !== summary.metadata.model_used && (
                        <span className="text-muted-foreground/70 text-[10px]">
                          (Requested: {summary.metadata.model_requested})
                        </span>
                      )}
                    </div>
                  ) : null}
                  {typeof summary.metadata.tokens_used === 'number' && (
                    <p>Tokens used: {summary.metadata.tokens_used.toLocaleString()}</p>
                  )}
                </div>
              )}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>

    {summaryId && (
      <SummaryPromptDialog
        guildId={guildId}
        summaryId={summaryId}
        open={promptDialogOpen}
        onOpenChange={setPromptDialogOpen}
      />
    )}

    {summaryId && summary && (
      <PushToChannelModal
        open={pushModalOpen}
        onOpenChange={setPushModalOpen}
        channels={channels}
        summaryTitle={`#${summary.channel_name} Summary`}
        isPending={pushSummary.isPending}
        onSubmit={handlePush}
      />
    )}
    </>
  );
}

function SummariesSkeleton() {
  return (
    <div className="grid gap-4">
      {[1, 2, 3].map((i) => (
        <Card key={i} className="border-border/50">
          <CardContent className="p-5">
            <div className="mb-3 flex justify-between">
              <div className="flex gap-2">
                <Skeleton className="h-5 w-24" />
                <Skeleton className="h-5 w-16" />
              </div>
              <Skeleton className="h-4 w-20" />
            </div>
            <Skeleton className="mb-4 h-10 w-full" />
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
