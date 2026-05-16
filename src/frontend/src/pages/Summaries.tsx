import { useState, useEffect, useCallback } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import { useGenerateSummary, useTaskStatus } from "@/hooks/useSummaries";
import { useGenerateArchive, useGenerationJob } from "@/hooks/useArchive";
import { useGuild } from "@/hooks/useGuilds";
import { usePromptTemplates } from "@/hooks/usePromptTemplates";
import { useWhatsAppChats } from "@/hooks/useWhatsApp";
import { useCreateSchedule } from "@/hooks/useSchedules";
import { SummaryWizard, type WizardState } from "@/components/summary-wizard";
import { generateScheduleName } from "@/components/summary-wizard/steps/WhenStep";
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
import { Sparkles, FileText, Loader2, Hash, FolderOpen, Server, Search, Archive as ArchiveIcon, FileCode, Calendar as CalendarIcon, ExternalLink, HelpCircle, MessageSquare } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { StoredSummariesTab } from "@/components/summaries/StoredSummariesTab";
import type { SummaryOptions, GenerateRequest } from "@/types";

export function Summaries() {
  const { id, summaryId: deepLinkSummaryId } = useParams<{ id: string; summaryId?: string }>();
  const [searchParams] = useSearchParams();
  const { data: guild } = useGuild(id || "");
  const { data: promptTemplates = [] } = usePromptTemplates(id || "");
  const { data: whatsappChats = [] } = useWhatsAppChats(id || "");
  const generateSummary = useGenerateSummary(id || "");
  const generateArchive = useGenerateArchive();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // ADR-009, ADR-012: Read source and highlight from URL params
  const sourceParam = searchParams.get("source");
  const highlightParam = searchParams.get("highlight");
  // Deep link: open specific summary from Jobs page or RSS feed
  const viewSummaryId = searchParams.get("view") || deepLinkSummaryId;

  // ADR-012: Default to "all" (All Summaries) tab - unified view
  const [activeTab, setActiveTab] = useState("all");

  const [generateOpen, setGenerateOpen] = useState(false);
  const [platform, setPlatform] = useState<"discord" | "slack" | "whatsapp">("discord");
  const [scope, setScope] = useState<"channel" | "category" | "guild">("channel");
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [timeRange, setTimeRange] = useState("24h");
  // ADR-035: Custom date range state
  const [useCustomDates, setUseCustomDates] = useState(false);
  const [customStartDate, setCustomStartDate] = useState<Date | undefined>();
  const [customEndDate, setCustomEndDate] = useState<Date | undefined>();
  const [summaryLength, setSummaryLength] = useState<SummaryOptions["summary_length"]>("detailed");
  const [perspective, setPerspective] = useState<SummaryOptions["perspective"]>("general");
  const [promptTemplateId, setPromptTemplateId] = useState<string | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);  // For archive retrospective jobs
  const [channelSearch, setChannelSearch] = useState("");

  // ADR-089: Unified Summary Wizard
  const [wizardOpen, setWizardOpen] = useState(false);
  const createSchedule = useCreateSchedule(id || "");

  // ADR-035: Track generation parameters for progress display
  const [generationParams, setGenerationParams] = useState<{
    scope: "channel" | "category" | "guild";
    channelCount: number;
    timeRange: string;
    perspective: string;
  } | null>(null);

  // Poll task status when generating
  const taskStatus = useTaskStatus(id || "", activeTaskId);
  const [taskStartTime, setTaskStartTime] = useState<number | null>(null);

  // Track when task starts
  useEffect(() => {
    if (activeTaskId && !taskStartTime) {
      setTaskStartTime(Date.now());
    } else if (!activeTaskId) {
      setTaskStartTime(null);
      setGenerationParams(null);
    }
  }, [activeTaskId, taskStartTime]);

  // ADR-043: Reset scope and clear selections when switching platforms
  useEffect(() => {
    if ((platform === "slack" || platform === "whatsapp") && scope === "category") {
      setScope("channel");
    }
    // Clear channel selections when switching platforms
    setSelectedChannels([]);
    setChannelSearch("");
  }, [platform]);

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

  // Track archive retrospective job status
  const archiveJob = useGenerationJob(activeJobId);
  useEffect(() => {
    if (!archiveJob.data) return;

    if (archiveJob.data.status === "completed") {
      queryClient.invalidateQueries({ queryKey: ["stored-summaries", id] });
      setActiveJobId(null);
      toast({
        title: "Retrospective complete!",
        description: `Generated ${archiveJob.data.completed || 0} summaries successfully.`,
      });
    } else if (archiveJob.data.status === "failed") {
      setActiveJobId(null);
      toast({
        title: "Retrospective failed",
        description: archiveJob.data.error || "Failed to generate retrospective summaries.",
        variant: "destructive",
      });
    }
  }, [archiveJob.data?.status, archiveJob.data?.completed, id, queryClient, toast]);

  // ADR-089: Wizard handlers
  const handleWizardGenerateNow = useCallback(async (state: WizardState) => {
    const hoursMap: Record<string, number> = { "4h": 4, "8h": 8, "24h": 24, "48h": 48 };
    const hours = state.timeRange === "custom" ? state.customHours || 24 : hoursMap[state.timeRange];

    const request: GenerateRequest = {
      scope: state.scope,
      time_range: { type: "hours", value: hours },
      options: {
        summary_length: state.summaryLength,
        include_action_items: true,
        include_technical_terms: true,
        min_messages: state.minMessages,
      },
      channel_ids: state.scope === "channel" ? state.channelIds : undefined,
      category_id: state.scope === "category" ? state.categoryId : undefined,
      platform: state.platform,
      ...(state.promptTemplateId && { prompt_template_id: state.promptTemplateId }),
    };

    const result = await generateSummary.mutateAsync(request);
    setActiveTaskId(result.task_id);
    toast({ title: "Generating", description: "Your summary is being generated..." });
  }, [generateSummary, toast]);

  const handleWizardCreateSchedule = useCallback(async (state: WizardState) => {
    // Use auto-generated name if user didn't provide one
    const scheduleName = state.scheduleName.trim() || generateScheduleName(state);
    await createSchedule.mutateAsync({
      name: scheduleName,
      scope: state.scope,
      channel_ids: state.scope === "channel" ? state.channelIds : [],
      category_id: state.scope === "category" ? state.categoryId : undefined,
      schedule_type: state.frequency,  // Pass frequency directly - supports all types
      schedule_time: state.scheduleTime,
      schedule_days: state.frequency === "weekly" ? state.scheduleDays : undefined,
      timezone: state.timezone,
      platform: state.platform,
      enable_continuity: state.enableContinuity,
      time_range_hours: state.lookbackHours,  // ADR-089: Lookback period
      prompt_template_id: state.promptTemplateId || undefined,  // ADR-034: Custom templates
      destinations: [
        { type: "dashboard", target: "default", format: "embed" },
        ...(state.destinations.discordChannel && state.destinations.discordChannelId
          ? [{ type: "discord_channel" as const, target: state.destinations.discordChannelId, format: "embed" as const }]
          : []),
        // ADR-047: Discord DM destination
        ...(state.destinations.discordDm && state.destinations.discordDmUserId
          ? [{ type: "discord_dm" as const, target: state.destinations.discordDmUserId, format: "embed" as const }]
          : []),
        ...(state.destinations.webhook && state.destinations.webhookUrl
          ? [{ type: "webhook" as const, target: state.destinations.webhookUrl, format: "json" as const }]
          : []),
        ...(state.destinations.email && state.destinations.emailAddresses
          ? [{ type: "email" as const, target: state.destinations.emailAddresses, format: "html" as const }]
          : []),
      ],
      summary_options: {
        summary_length: state.summaryLength,
        perspective: state.perspective,  // Pass perspective directly
        include_action_items: true,
        include_technical_terms: true,
        min_messages: state.minMessages,
      },
    });
    toast({ title: "Schedule created", description: `${scheduleName} has been scheduled.` });
  }, [createSchedule, toast]);

  const handleWizardGeneratePast = useCallback(async (state: WizardState) => {
    if (!state.dateFrom || !state.dateTo || !id) return;

    // For weekly/daily granularity, use the archive generator which handles batch generation
    if (state.pastGranularity === "weekly" || state.pastGranularity === "daily") {
      // Map weekly days to specific dates within the range
      const archiveRequest = {
        source_type: state.platform,
        server_id: id,
        scope: state.scope,
        channel_ids: state.scope === "channel" ? state.channelIds : undefined,
        category_id: state.scope === "category" ? state.categoryId : undefined,
        date_range: {
          start: state.dateFrom.toISOString().split("T")[0],
          end: state.dateTo.toISOString().split("T")[0],
        },
        granularity: state.pastGranularity,
        // For weekly, pass the selected days (0=Sun, 6=Sat)
        // The backend will generate summaries for each matching day in the range
        schedule_days: state.pastGranularity === "weekly" ? state.pastScheduleDays : undefined,
        // Lookback hours determines how many hours each summary covers
        lookback_hours: state.pastLookbackHours,
        summary_type: state.summaryLength,
        skip_existing: true,
      };

      const result = await generateArchive.mutateAsync(archiveRequest);
      setActiveJobId(result.id);

      const granularityLabel = state.pastGranularity === "weekly"
        ? `weekly (${state.pastScheduleDays.map(d => ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][d]).join(", ")})`
        : "daily";
      toast({
        title: "Retrospective Started",
        description: `Generating ${granularityLabel} summaries for the selected period...`
      });
      return;
    }

    // For single summary, use the regular summary API
    const request: GenerateRequest = {
      scope: state.scope,
      time_range: {
        type: "custom",
        start: state.dateFrom.toISOString(),
        end: state.dateTo.toISOString(),
      },
      options: {
        summary_length: state.summaryLength,
        include_action_items: true,
        include_technical_terms: true,
        min_messages: state.minMessages,
      },
      channel_ids: state.scope === "channel" ? state.channelIds : undefined,
      category_id: state.scope === "category" ? state.categoryId : undefined,
      platform: state.platform,
      ...(state.promptTemplateId && { prompt_template_id: state.promptTemplateId }),
    };

    const result = await generateSummary.mutateAsync(request);
    setActiveTaskId(result.task_id);
    toast({ title: "Generating", description: "Your retrospective summary is being generated..." });
  }, [generateSummary, generateArchive, toast, id]);

  const handleGenerate = async () => {
    try {
      // ADR-035: Build time_range based on mode
      let timeRangeParam: GenerateRequest["time_range"];

      if (useCustomDates && customStartDate && customEndDate) {
        // Custom date range - set times to start/end of day
        const startOfDay = new Date(customStartDate);
        startOfDay.setHours(0, 0, 0, 0);
        const endOfDay = new Date(customEndDate);
        endOfDay.setHours(23, 59, 59, 999);

        timeRangeParam = {
          type: "custom",
          start: startOfDay.toISOString(),
          end: endOfDay.toISOString(),
        };
      } else {
        // Relative time range (quick preset)
        const timeValue = parseInt(timeRange.replace(/\D/g, ""));
        const timeType = timeRange.includes("d") ? "days" : "hours";
        timeRangeParam = {
          type: timeType as "hours" | "days",
          value: timeValue,
        };
      }

      const request: GenerateRequest = {
        scope,
        time_range: timeRangeParam,
        options: {
          summary_length: summaryLength,
          include_action_items: true,
          include_technical_terms: true,
        },
        // ADR-034: Include custom template if selected
        ...(promptTemplateId && { prompt_template_id: promptTemplateId }),
        // ADR-043: Include platform for Slack support
        platform,
      };

      // Add scope-specific fields
      if (scope === "channel") {
        if (selectedChannels.length > 0) {
          request.channel_ids = selectedChannels;
        } else if (platform === "discord") {
          // Default to enabled Discord channels
          request.channel_ids = guild?.config.enabled_channels || [];
        } else if (platform === "whatsapp") {
          // Default to all imported WhatsApp chats (backend resolves this)
          request.channel_ids = whatsappChats.map(c => c.chat_id);
        }
        // For Slack, backend handles channel resolution
      } else if (scope === "category") {
        request.category_id = selectedCategory;
      }
      // For "guild" scope, no additional fields needed
      
      const result = await generateSummary.mutateAsync(request);
      
      // Store task ID for polling
      setActiveTaskId(result.task_id);

      // ADR-035: Store generation parameters for progress display
      const selectedTemplate = promptTemplateId
        ? promptTemplates.find(t => t.id === promptTemplateId)?.name
        : null;
      const timeDisplay = useCustomDates && customStartDate && customEndDate
        ? `${format(customStartDate, "MMM d")} - ${format(customEndDate, "MMM d")}`
        : timeRange;
      const channelCount = scope === "channel"
        ? (selectedChannels.length || (platform === "whatsapp" ? whatsappChats.length : guild?.config.enabled_channels?.length) || 0)
        : scope === "category"
        ? (guild?.categories.find(c => c.id === selectedCategory)?.channel_count || 0)
        : (platform === "whatsapp" ? whatsappChats.length : guild?.channels?.filter(c => c.type === "text").length || 0);

      setGenerationParams({
        scope,
        channelCount,
        timeRange: timeDisplay,
        perspective: selectedTemplate || perspective,
      });

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
        {/* ADR-089: Unified Summary Wizard */}
        <Button onClick={() => setWizardOpen(true)}>
          <Sparkles className="mr-2 h-4 w-4" />
          Create Summary
        </Button>

        <SummaryWizard
          open={wizardOpen}
          onOpenChange={setWizardOpen}
          guildId={id || ""}
          initialWhenType="now"
          onGenerateNow={handleWizardGenerateNow}
          onCreateSchedule={handleWizardCreateSchedule}
          onGeneratePast={handleWizardGeneratePast}
        />

        {/* Legacy dialog - kept for reference, hidden */}
        <Dialog open={generateOpen} onOpenChange={setGenerateOpen}>
          <DialogTrigger asChild>
            <span className="hidden" />
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Generate Summary</DialogTitle>
              <DialogDescription>
                Configure your summary options
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              {/* Platform Selector - ADR-043 */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Platform</label>
                <div className="grid grid-cols-3 gap-2">
                  <Button
                    type="button"
                    variant={platform === "discord" ? "default" : "outline"}
                    size="sm"
                    className="w-full"
                    onClick={() => setPlatform("discord")}
                  >
                    <MessageSquare className="mr-1.5 h-3.5 w-3.5" />
                    Discord
                  </Button>
                  <Button
                    type="button"
                    variant={platform === "slack" ? "default" : "outline"}
                    size="sm"
                    className="w-full"
                    onClick={() => setPlatform("slack")}
                  >
                    <Hash className="mr-1.5 h-3.5 w-3.5" />
                    Slack
                  </Button>
                  <Button
                    type="button"
                    variant={platform === "whatsapp" ? "default" : "outline"}
                    size="sm"
                    className="w-full"
                    onClick={() => setPlatform("whatsapp")}
                  >
                    <MessageSquare className="mr-1.5 h-3.5 w-3.5" />
                    WhatsApp
                  </Button>
                </div>
              </div>

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
                    disabled={platform === "slack" || platform === "whatsapp"}
                    title={platform !== "discord" ? `${platform === "slack" ? "Slack" : "WhatsApp"} doesn't have categories` : undefined}
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
              {scope === "channel" && platform === "slack" && (
                <div className="rounded-md border border-purple-500/20 bg-purple-500/5 p-3">
                  <p className="text-sm text-muted-foreground">
                    All public Slack channels will be summarized.
                    Channel selection for Slack coming soon.
                  </p>
                </div>
              )}
              {scope === "channel" && platform === "whatsapp" && (
                <div className="space-y-2">
                  <label className="text-sm font-medium">WhatsApp Chats</label>
                  {whatsappChats.length > 0 ? (
                    <>
                      <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                          placeholder="Search chats..."
                          value={channelSearch}
                          onChange={(e) => setChannelSearch(e.target.value)}
                          className="pl-8"
                        />
                      </div>
                      <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">
                        {whatsappChats
                          .filter(c => c.chat_name.toLowerCase().includes(channelSearch.toLowerCase()))
                          .map((chat) => (
                            <div key={chat.chat_id} className="flex items-center space-x-2">
                              <Checkbox
                                id={chat.chat_id}
                                checked={selectedChannels.includes(chat.chat_id)}
                                onCheckedChange={(checked) => {
                                  if (checked) {
                                    setSelectedChannels([...selectedChannels, chat.chat_id]);
                                  } else {
                                    setSelectedChannels(selectedChannels.filter(id => id !== chat.chat_id));
                                  }
                                }}
                              />
                              <label htmlFor={chat.chat_id} className="text-sm cursor-pointer flex-1">
                                {chat.chat_name}
                                <span className="text-muted-foreground ml-2">
                                  ({chat.total_messages} msgs)
                                </span>
                              </label>
                            </div>
                          ))}
                        {whatsappChats
                          .filter(c => c.chat_name.toLowerCase().includes(channelSearch.toLowerCase()))
                          .length === 0 && (
                          <p className="text-sm text-muted-foreground py-2 text-center">
                            No chats match "{channelSearch}"
                          </p>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {selectedChannels.length === 0
                          ? "All imported chats will be included"
                          : `${selectedChannels.length} chat(s) selected`}
                      </p>
                    </>
                  ) : (
                    <div className="rounded-md border border-yellow-500/20 bg-yellow-500/5 p-3">
                      <p className="text-sm text-muted-foreground">
                        No WhatsApp chats imported yet. Go to{" "}
                        <a href={`/guilds/${id}/whatsapp`} className="text-primary hover:underline">
                          WhatsApp Imports
                        </a>{" "}
                        to upload chat exports.
                      </p>
                    </div>
                  )}
                </div>
              )}
              {scope === "channel" && platform === "discord" && guild?.channels && (
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

              {/* Guild/Workspace scope info */}
              {scope === "guild" && (
                <div className={cn(
                  "rounded-md border p-3",
                  platform === "slack" ? "border-purple-500/20 bg-purple-500/5" : "border-primary/20 bg-primary/5"
                )}>
                  <p className="text-sm text-muted-foreground">
                    {platform === "slack"
                      ? "All public Slack channels in the connected workspace will be summarized."
                      : "All enabled channels across the server will be summarized."}
                  </p>
                </div>
              )}

              {/* ADR-035: Time Range with custom date support */}
              <div className="space-y-3">
                <label className="text-sm font-medium">Time Range</label>

                {/* Quick presets */}
                <div className="flex flex-wrap gap-2">
                  {[
                    { value: "1h", label: "1h" },
                    { value: "6h", label: "6h" },
                    { value: "12h", label: "12h" },
                    { value: "24h", label: "24h" },
                    { value: "48h", label: "48h" },
                    { value: "7d", label: "7d" },
                  ].map((preset) => (
                    <Button
                      key={preset.value}
                      type="button"
                      variant={!useCustomDates && timeRange === preset.value ? "default" : "outline"}
                      size="sm"
                      onClick={() => {
                        setUseCustomDates(false);
                        setTimeRange(preset.value);
                      }}
                    >
                      {preset.label}
                    </Button>
                  ))}
                </div>

                {/* Custom date range */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="custom-dates"
                      checked={useCustomDates}
                      onCheckedChange={(checked) => setUseCustomDates(checked === true)}
                    />
                    <label htmlFor="custom-dates" className="text-sm cursor-pointer">
                      Custom date range
                    </label>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="right" className="max-w-[200px]">
                        <p>Defaults to today. Selecting a start date will auto-set the end date to match.</p>
                      </TooltipContent>
                    </Tooltip>
                  </div>

                  {useCustomDates && (
                    <div className="flex gap-2 items-center">
                      <Popover>
                        <PopoverTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            className={cn(
                              "w-[130px] justify-start text-left font-normal",
                              !customStartDate && "text-muted-foreground"
                            )}
                          >
                            <CalendarIcon className="mr-2 h-4 w-4" />
                            {customStartDate ? format(customStartDate, "MMM d, yyyy") : "Start date"}
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0" align="start">
                          <Calendar
                            mode="single"
                            selected={customStartDate}
                            onSelect={(date) => {
                              setCustomStartDate(date);
                              // Auto-set end date to match start date for single-day selection UX
                              if (date && !customEndDate) {
                                setCustomEndDate(date);
                              }
                            }}
                            disabled={(date) => date > new Date() || (customEndDate ? date > customEndDate : false)}
                            initialFocus
                          />
                        </PopoverContent>
                      </Popover>
                      <span className="text-muted-foreground">to</span>
                      <Popover>
                        <PopoverTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            className={cn(
                              "w-[130px] justify-start text-left font-normal",
                              !customEndDate && "text-muted-foreground"
                            )}
                          >
                            <CalendarIcon className="mr-2 h-4 w-4" />
                            {customEndDate ? format(customEndDate, "MMM d, yyyy") : "End date"}
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0" align="start">
                          <Calendar
                            mode="single"
                            selected={customEndDate}
                            onSelect={setCustomEndDate}
                            disabled={(date) => date > new Date() || (customStartDate ? date < customStartDate : false)}
                          />
                        </PopoverContent>
                      </Popover>
                    </div>
                  )}
                </div>
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

              {/* ADR-034: Combined Perspective + Custom Templates */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Perspective</label>
                <Select
                  value={promptTemplateId ? `template:${promptTemplateId}` : perspective}
                  onValueChange={(v) => {
                    if (v.startsWith("template:")) {
                      setPromptTemplateId(v.replace("template:", ""));
                      setPerspective("general");
                    } else {
                      setPromptTemplateId(null);
                      setPerspective(v as SummaryOptions["perspective"]);
                    }
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">General</SelectItem>
                    <SelectItem value="developer">Developer</SelectItem>
                    <SelectItem value="marketing">Marketing</SelectItem>
                    <SelectItem value="executive">Executive</SelectItem>
                    <SelectItem value="support">Support</SelectItem>
                    {promptTemplates.length > 0 && (
                      <>
                        <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground border-t mt-1 pt-2">
                          Custom Perspectives
                        </div>
                        {promptTemplates.map((template) => (
                          <SelectItem key={template.id} value={`template:${template.id}`}>
                            <span className="flex items-center gap-2">
                              <FileCode className="h-3 w-3" />
                              {template.name}
                            </span>
                          </SelectItem>
                        ))}
                      </>
                    )}
                  </SelectContent>
                </Select>
                {promptTemplateId && (
                  <p className="text-xs text-muted-foreground">
                    Using custom template. Summary length still controls model selection.
                  </p>
                )}
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

      {/* Generation Progress - ADR-035: Show parameters, ADR-040: Link to Jobs */}
      {activeTaskId && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <Card className="border-primary/50 bg-primary/5">
            <CardContent className="flex items-center gap-3 p-4">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <div className="flex-1">
                <p className="font-medium">Generating summary...</p>
                {generationParams ? (
                  <p className="text-sm text-muted-foreground">
                    {generationParams.scope === "guild" ? "Server-wide" :
                     generationParams.scope === "category" ? "Category" :
                     `${generationParams.channelCount} channel${generationParams.channelCount !== 1 ? "s" : ""}`}
                    {" · "}
                    {generationParams.timeRange}
                    {" · "}
                    {generationParams.perspective}
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">This may take a moment</p>
                )}
              </div>
              <Button variant="ghost" size="sm" asChild>
                <a href={`/guilds/${id}/jobs`} className="flex items-center gap-1.5">
                  View in Jobs
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </Button>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* ADR-012, ADR-040: Consolidated Tabs - All Summaries + Retrospective (Jobs moved to sidebar) */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="all" className="gap-2">
            <FileText className="h-4 w-4" />
            All Summaries
          </TabsTrigger>
          <TabsTrigger value="retrospective" className="gap-2">
            <ArchiveIcon className="h-4 w-4" />
            Retrospective
          </TabsTrigger>
        </TabsList>

        {/* All Summaries Tab - Unified view (ADR-012) */}
        <TabsContent value="all">
          <StoredSummariesTab guildId={id || ""} initialSource={sourceParam as "archive" | "scheduled" | "manual" | undefined} viewSummaryId={viewSummaryId} />
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

