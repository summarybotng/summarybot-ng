import { useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { format, subDays } from "date-fns";
import {
  useArchiveSources,
  useScanSource,
  useEstimateCost,
  useGenerateArchive,
  useGenerationJob,
  useCancelJob,
  useCostReport,
  useImportWhatsApp,
  useSyncStatus,
  useDriveStatus,
  useOAuthConfig,
  useServerSyncConfig,
  useStartOAuth,
  useDisconnectDrive,
  useConfigureServerSync,
  useTriggerSync,
  useDriveFolders,
  type ArchiveSource,
  type GenerateRequest,
} from "@/hooks/useArchive";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import {
  Archive as ArchiveIcon,
  FolderOpen,
  Calendar,
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Play,
  Square,
  Upload,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Loader2,
  FileText,
  MessageSquare,
  Cloud,
  CloudOff,
  Link,
  Unlink,
  ExternalLink,
  Settings,
  HardDrive,
  Folder,
} from "lucide-react";

export function Archive() {
  const { id: guildId } = useParams<{ id: string }>();
  const { toast } = useToast();

  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  // Queries
  const { data: sources, isLoading: sourcesLoading, refetch: refetchSources } = useArchiveSources();
  const { data: scanResult, isLoading: scanLoading } = useScanSource(selectedSource || "");
  const { data: costReport } = useCostReport();
  const { data: activeJob } = useGenerationJob(activeJobId);

  // Mutations
  const estimateCost = useEstimateCost();
  const generateArchive = useGenerateArchive();
  const cancelJob = useCancelJob();
  const importWhatsApp = useImportWhatsApp();

  // Filter sources for this guild
  const guildSources = sources?.filter(s => s.server_id === guildId) || [];

  // Handle job completion
  if (activeJob?.status === "completed" || activeJob?.status === "failed") {
    if (activeJobId) {
      toast({
        title: activeJob.status === "completed" ? "Generation complete" : "Generation failed",
        description: activeJob.status === "completed"
          ? `Generated ${activeJob.progress.completed} summaries`
          : activeJob.error || "An error occurred",
        variant: activeJob.status === "completed" ? "default" : "destructive",
      });
      setActiveJobId(null);
      refetchSources();
    }
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
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ArchiveIcon className="h-6 w-6" />
            Archive
          </h1>
          <p className="text-muted-foreground">
            Retrospective summaries, backfill, and historical data
          </p>
        </div>
        <div className="flex gap-2">
          <Dialog open={importOpen} onOpenChange={setImportOpen}>
            <DialogTrigger asChild>
              <Button variant="outline">
                <Upload className="mr-2 h-4 w-4" />
                Import
              </Button>
            </DialogTrigger>
            <ImportDialog
              onImport={async (file, groupId, groupName, format) => {
                try {
                  await importWhatsApp.mutateAsync({ file, groupId, groupName, format });
                  toast({
                    title: "Import successful",
                    description: "WhatsApp chat has been imported",
                  });
                  setImportOpen(false);
                  refetchSources();
                } catch {
                  toast({
                    title: "Import failed",
                    description: "Failed to import chat data",
                    variant: "destructive",
                  });
                }
              }}
              isPending={importWhatsApp.isPending}
            />
          </Dialog>
          <Dialog open={generateOpen} onOpenChange={setGenerateOpen}>
            <DialogTrigger asChild>
              <Button>
                <Play className="mr-2 h-4 w-4" />
                Generate
              </Button>
            </DialogTrigger>
            <GenerateDialog
              guildId={guildId || ""}
              sources={guildSources}
              onEstimate={async (request) => {
                const result = await estimateCost.mutateAsync(request);
                return result;
              }}
              onGenerate={async (request) => {
                const job = await generateArchive.mutateAsync(request);
                setActiveJobId(job.job_id);
                setGenerateOpen(false);
                toast({
                  title: "Generation started",
                  description: `Job ${job.job_id} is now running`,
                });
              }}
              isPending={generateArchive.isPending}
            />
          </Dialog>
        </div>
      </motion.div>

      {/* Active Job Progress */}
      {activeJob && (activeJob.status === "pending" || activeJob.status === "running") && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <Card className="border-primary/50 bg-primary/5">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                  <div>
                    <p className="font-medium">Generating archive summaries...</p>
                    <p className="text-sm text-muted-foreground">
                      {activeJob.progress.completed} of {activeJob.progress.total} complete
                    </p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => cancelJob.mutate(activeJob.job_id)}
                >
                  <Square className="mr-2 h-4 w-4" />
                  Cancel
                </Button>
              </div>
              <Progress
                value={(activeJob.progress.completed / activeJob.progress.total) * 100}
                className="h-2"
              />
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="sources" className="space-y-4">
        <TabsList>
          <TabsTrigger value="sources" className="gap-2">
            <FolderOpen className="h-4 w-4" />
            Sources
          </TabsTrigger>
          <TabsTrigger value="costs" className="gap-2">
            <DollarSign className="h-4 w-4" />
            Costs
          </TabsTrigger>
          <TabsTrigger value="sync" className="gap-2">
            <Cloud className="h-4 w-4" />
            Sync
          </TabsTrigger>
        </TabsList>

        {/* Sources Tab */}
        <TabsContent value="sources" className="space-y-4">
          {sourcesLoading ? (
            <SourcesSkeleton />
          ) : guildSources.length === 0 ? (
            <EmptyState onImport={() => setImportOpen(true)} />
          ) : (
            <div className="grid gap-4">
              {guildSources.map((source, index) => (
                <SourceCard
                  key={source.source_key}
                  source={source}
                  index={index}
                  isSelected={selectedSource === source.source_key}
                  onSelect={() => setSelectedSource(
                    selectedSource === source.source_key ? null : source.source_key
                  )}
                  scanResult={selectedSource === source.source_key ? scanResult : undefined}
                  scanLoading={selectedSource === source.source_key && scanLoading}
                />
              ))}
            </div>
          )}
        </TabsContent>

        {/* Costs Tab */}
        <TabsContent value="costs">
          <CostsView report={costReport} />
        </TabsContent>

        {/* Sync Tab */}
        <TabsContent value="sync">
          <SyncSettings guildId={guildId || ""} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// Source Card Component
function SourceCard({
  source,
  index,
  isSelected,
  onSelect,
  scanResult,
  scanLoading,
}: {
  source: ArchiveSource;
  index: number;
  isSelected: boolean;
  onSelect: () => void;
  scanResult?: ReturnType<typeof useScanSource>["data"];
  scanLoading: boolean;
}) {
  const sourceTypeIcons: Record<string, string> = {
    discord: "Discord",
    whatsapp: "WhatsApp",
    slack: "Slack",
    telegram: "Telegram",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Collapsible open={isSelected} onOpenChange={onSelect}>
        <Card className={`border-border/50 transition-all ${isSelected ? "border-primary/50" : ""}`}>
          <CollapsibleTrigger asChild>
            <CardHeader className="cursor-pointer hover:bg-muted/30 transition-colors">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {isSelected ? (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  )}
                  <div>
                    <CardTitle className="text-base flex items-center gap-2">
                      {source.server_name}
                      {source.channel_name && (
                        <span className="text-muted-foreground font-normal">
                          / #{source.channel_name}
                        </span>
                      )}
                    </CardTitle>
                    <CardDescription className="flex items-center gap-2 mt-1">
                      <Badge variant="outline" className="text-xs">
                        {sourceTypeIcons[source.source_type] || source.source_type}
                      </Badge>
                      <span>{source.summary_count} summaries</span>
                      {source.date_range && (
                        <span>
                          {source.date_range.start} - {source.date_range.end}
                        </span>
                      )}
                    </CardDescription>
                  </div>
                </div>
              </div>
            </CardHeader>
          </CollapsibleTrigger>

          <CollapsibleContent>
            <CardContent className="border-t pt-4">
              {scanLoading ? (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Scanning...
                </div>
              ) : scanResult ? (
                <div className="space-y-4">
                  {/* Summary Stats */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <StatBox
                      icon={CheckCircle2}
                      label="Complete"
                      value={scanResult.complete}
                      color="text-green-500"
                    />
                    <StatBox
                      icon={XCircle}
                      label="Failed"
                      value={scanResult.failed}
                      color="text-red-500"
                    />
                    <StatBox
                      icon={Clock}
                      label="Missing"
                      value={scanResult.missing}
                      color="text-yellow-500"
                    />
                    <StatBox
                      icon={AlertTriangle}
                      label="Outdated"
                      value={scanResult.outdated}
                      color="text-orange-500"
                    />
                  </div>

                  {/* Gaps */}
                  {scanResult.gaps.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-2">Gaps to fill:</h4>
                      <div className="space-y-2 max-h-40 overflow-y-auto">
                        {scanResult.gaps.slice(0, 10).map((gap, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between text-sm bg-muted/30 rounded px-3 py-2"
                          >
                            <span>
                              {gap.start_date} - {gap.end_date}
                            </span>
                            <div className="flex items-center gap-2">
                              <Badge
                                variant={
                                  gap.type === "missing" ? "secondary" :
                                  gap.type === "failed" ? "destructive" : "outline"
                                }
                              >
                                {gap.type}
                              </Badge>
                              <span className="text-muted-foreground">{gap.days} days</span>
                            </div>
                          </div>
                        ))}
                        {scanResult.gaps.length > 10 && (
                          <p className="text-sm text-muted-foreground text-center py-2">
                            +{scanResult.gaps.length - 10} more gaps
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {scanResult.gaps.length === 0 && scanResult.complete > 0 && (
                    <div className="flex items-center gap-2 text-green-600">
                      <CheckCircle2 className="h-4 w-4" />
                      <span>Archive is complete - no gaps found!</span>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-muted-foreground">Click to scan for gaps</p>
              )}
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>
    </motion.div>
  );
}

function StatBox({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: typeof CheckCircle2;
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon className={`h-4 w-4 ${color}`} />
      <div>
        <p className="text-lg font-semibold">{value}</p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

// Generate Dialog
function GenerateDialog({
  guildId,
  sources,
  onEstimate,
  onGenerate,
  isPending,
}: {
  guildId: string;
  sources: ArchiveSource[];
  onEstimate: (request: GenerateRequest) => Promise<{ periods: number; estimated_cost_usd: number; estimated_tokens: number; model: string }>;
  onGenerate: (request: GenerateRequest) => Promise<void>;
  isPending: boolean;
}) {
  const [sourceType, setSourceType] = useState("discord");
  const [startDate, setStartDate] = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
  const [endDate, setEndDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [model, setModel] = useState("anthropic/claude-3-haiku");
  const [skipExisting, setSkipExisting] = useState(true);
  const [regenerateFailed, setRegenerateFailed] = useState(true);
  const [maxCost, setMaxCost] = useState<string>("");
  const [estimate, setEstimate] = useState<{ periods: number; estimated_cost_usd: number; estimated_tokens: number; model: string } | null>(null);
  const [estimating, setEstimating] = useState(false);

  const handleEstimate = async () => {
    setEstimating(true);
    try {
      const result = await onEstimate({
        source_type: sourceType,
        server_id: guildId,
        date_range: { start: startDate, end: endDate },
        model,
        skip_existing: skipExisting,
        regenerate_failed: regenerateFailed,
        dry_run: true,
      });
      setEstimate(result);
    } catch {
      setEstimate(null);
    }
    setEstimating(false);
  };

  const handleGenerate = () => {
    onGenerate({
      source_type: sourceType,
      server_id: guildId,
      date_range: { start: startDate, end: endDate },
      model,
      skip_existing: skipExisting,
      regenerate_failed: regenerateFailed,
      max_cost_usd: maxCost ? parseFloat(maxCost) : undefined,
    });
  };

  return (
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Generate Archive Summaries</DialogTitle>
        <DialogDescription>
          Generate retrospective summaries for a date range
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4 py-4">
        <div className="space-y-2">
          <Label>Source Type</Label>
          <Select value={sourceType} onValueChange={setSourceType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="discord">Discord</SelectItem>
              <SelectItem value="whatsapp">WhatsApp</SelectItem>
              <SelectItem value="slack">Slack</SelectItem>
              <SelectItem value="telegram">Telegram</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Start Date</Label>
            <Input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>End Date</Label>
            <Input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label>Model</Label>
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="anthropic/claude-3-haiku">Claude 3 Haiku (fastest, cheapest)</SelectItem>
              <SelectItem value="anthropic/claude-3.5-sonnet">Claude 3.5 Sonnet (balanced)</SelectItem>
              <SelectItem value="anthropic/claude-3-opus">Claude 3 Opus (best quality)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label htmlFor="skip-existing">Skip existing summaries</Label>
            <Switch
              id="skip-existing"
              checked={skipExisting}
              onCheckedChange={setSkipExisting}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label htmlFor="regenerate-failed">Regenerate failed summaries</Label>
            <Switch
              id="regenerate-failed"
              checked={regenerateFailed}
              onCheckedChange={setRegenerateFailed}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label>Max Cost (USD, optional)</Label>
          <Input
            type="number"
            step="0.01"
            placeholder="e.g., 5.00"
            value={maxCost}
            onChange={(e) => setMaxCost(e.target.value)}
          />
        </div>

        {/* Cost Estimate */}
        {estimate && (
          <div className="rounded-md border bg-muted/30 p-3 space-y-1">
            <p className="text-sm font-medium">Estimated Cost</p>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <span className="text-muted-foreground">Periods:</span>
              <span>{estimate.periods}</span>
              <span className="text-muted-foreground">Tokens:</span>
              <span>{estimate.estimated_tokens.toLocaleString()}</span>
              <span className="text-muted-foreground">Cost:</span>
              <span className="font-semibold">${estimate.estimated_cost_usd.toFixed(4)}</span>
            </div>
          </div>
        )}
      </div>

      <DialogFooter className="gap-2">
        <Button variant="outline" onClick={handleEstimate} disabled={estimating}>
          {estimating ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <DollarSign className="mr-2 h-4 w-4" />
          )}
          Estimate
        </Button>
        <Button onClick={handleGenerate} disabled={isPending}>
          {isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          Generate
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

// Import Dialog
function ImportDialog({
  onImport,
  isPending,
}: {
  onImport: (file: File, groupId: string, groupName: string, format: "whatsapp_txt" | "reader_bot") => Promise<void>;
  isPending: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [groupId, setGroupId] = useState("");
  const [groupName, setGroupName] = useState("");
  const [format, setFormat] = useState<"whatsapp_txt" | "reader_bot">("whatsapp_txt");

  const handleSubmit = () => {
    if (file && groupId && groupName) {
      onImport(file, groupId, groupName, format);
    }
  };

  return (
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Import Chat Data</DialogTitle>
        <DialogDescription>
          Import WhatsApp chat exports for archiving
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4 py-4">
        <div className="space-y-2">
          <Label>Chat Export File</Label>
          <Input
            type="file"
            accept=".txt,.json"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </div>

        <div className="space-y-2">
          <Label>Format</Label>
          <Select value={format} onValueChange={(v) => setFormat(v as typeof format)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="whatsapp_txt">WhatsApp .txt Export</SelectItem>
              <SelectItem value="reader_bot">Reader Bot JSON</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Group ID</Label>
          <Input
            placeholder="e.g., family-group"
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label>Group Name</Label>
          <Input
            placeholder="e.g., Family Group Chat"
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
          />
        </div>
      </div>

      <DialogFooter>
        <Button
          onClick={handleSubmit}
          disabled={isPending || !file || !groupId || !groupName}
        >
          {isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Upload className="mr-2 h-4 w-4" />
          )}
          Import
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

// Costs View
function CostsView({ report }: { report?: ReturnType<typeof useCostReport>["data"] }) {
  if (!report) {
    return (
      <Card className="border-border/50">
        <CardContent className="flex flex-col items-center justify-center py-12">
          <DollarSign className="h-12 w-12 text-muted-foreground/30 mb-4" />
          <p className="text-muted-foreground">No cost data available yet</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Total */}
      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <DollarSign className="h-5 w-5" />
            Total Costs
          </CardTitle>
          <CardDescription>Period: {report.period}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <p className="text-3xl font-bold">${report.total_cost_usd.toFixed(4)}</p>
              <p className="text-sm text-muted-foreground">Total spent</p>
            </div>
            <div>
              <p className="text-3xl font-bold">{report.total_summaries.toLocaleString()}</p>
              <p className="text-sm text-muted-foreground">Total summaries</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* By Source */}
      {report.sources.length > 0 && (
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle>By Source</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {report.sources.map((source) => (
                <div
                  key={source.source_key}
                  className="flex items-center justify-between py-2 border-b last:border-0"
                >
                  <div>
                    <p className="font-medium">{source.server_name}</p>
                    <p className="text-sm text-muted-foreground">
                      {source.summary_count} summaries
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold">${source.total_cost_usd.toFixed(4)}</p>
                    <p className="text-sm text-muted-foreground">
                      This month: ${source.current_month.cost_usd.toFixed(4)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// Empty State
function EmptyState({ onImport }: { onImport: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col items-center justify-center py-20"
    >
      <ArchiveIcon className="mb-4 h-16 w-16 text-muted-foreground/30" />
      <h2 className="mb-2 text-xl font-semibold">No archive sources yet</h2>
      <p className="mb-6 text-center text-muted-foreground max-w-md">
        Import WhatsApp chats or generate retrospective summaries to build your archive
      </p>
      <Button onClick={onImport}>
        <Upload className="mr-2 h-4 w-4" />
        Import Chat Data
      </Button>
    </motion.div>
  );
}

// Loading Skeleton
function SourcesSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <Card key={i} className="border-border/50">
          <CardHeader>
            <div className="flex items-center gap-3">
              <Skeleton className="h-4 w-4" />
              <div className="space-y-2">
                <Skeleton className="h-5 w-48" />
                <Skeleton className="h-4 w-32" />
              </div>
            </div>
          </CardHeader>
        </Card>
      ))}
    </div>
  );
}

// ==================== Sync Settings Component ====================

function SyncSettings({ guildId }: { guildId: string }) {
  const { toast } = useToast();
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [folderPath, setFolderPath] = useState<{ id: string; name: string }[]>([
    { id: "root", name: "My Drive" },
  ]);

  // Queries
  const { data: syncStatus, isLoading: syncStatusLoading } = useSyncStatus();
  const { data: driveStatus } = useDriveStatus();
  const { data: oauthConfig } = useOAuthConfig();
  const { data: serverConfig, refetch: refetchServerConfig } = useServerSyncConfig(guildId);
  const { data: foldersData, isLoading: foldersLoading } = useDriveFolders(
    guildId,
    folderPath[folderPath.length - 1]?.id || "root"
  );

  // Mutations
  const startOAuth = useStartOAuth();
  const disconnectDrive = useDisconnectDrive();
  const configureSync = useConfigureServerSync();
  const triggerSync = useTriggerSync();

  const handleConnectDrive = async () => {
    try {
      // For now, use a placeholder user ID - in production this would come from auth
      const result = await startOAuth.mutateAsync({
        serverId: guildId,
        userId: "dashboard_user",
      });

      // Open OAuth URL in new window
      window.open(result.auth_url, "_blank", "width=600,height=700");

      toast({
        title: "Authorization started",
        description: "Complete the authorization in the popup window, then return here.",
      });
    } catch (error) {
      toast({
        title: "Failed to start authorization",
        description: "Please try again",
        variant: "destructive",
      });
    }
  };

  const handleDisconnect = async () => {
    try {
      await disconnectDrive.mutateAsync(guildId);
      toast({
        title: "Disconnected",
        description: "Google Drive has been disconnected",
      });
      refetchServerConfig();
    } catch {
      toast({
        title: "Failed to disconnect",
        variant: "destructive",
      });
    }
  };

  const handleSelectFolder = async (folderId: string, folderName: string) => {
    try {
      await configureSync.mutateAsync({
        serverId: guildId,
        folderId,
        folderName,
      });
      toast({
        title: "Folder configured",
        description: `Archives will sync to "${folderName}"`,
      });
      setSelectedFolder(null);
      refetchServerConfig();
    } catch {
      toast({
        title: "Failed to configure folder",
        variant: "destructive",
      });
    }
  };

  const handleTriggerSync = async () => {
    try {
      const result = await triggerSync.mutateAsync(`discord:${guildId}`);
      toast({
        title: "Sync complete",
        description: `Synced ${result.files_synced} files`,
      });
    } catch {
      toast({
        title: "Sync failed",
        variant: "destructive",
      });
    }
  };

  const navigateToFolder = (folderId: string, folderName: string) => {
    setFolderPath([...folderPath, { id: folderId, name: folderName }]);
  };

  const navigateBack = (index: number) => {
    setFolderPath(folderPath.slice(0, index + 1));
  };

  if (syncStatusLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading sync settings...
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Global Sync Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="h-5 w-5" />
            Google Drive Sync
          </CardTitle>
          <CardDescription>
            Sync your archive summaries to Google Drive for backup and sharing
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Connection Status */}
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div className="flex items-center gap-3">
              {serverConfig?.enabled && !serverConfig.using_fallback ? (
                <Cloud className="h-8 w-8 text-green-500" />
              ) : syncStatus?.configured ? (
                <Cloud className="h-8 w-8 text-blue-500" />
              ) : (
                <CloudOff className="h-8 w-8 text-muted-foreground" />
              )}
              <div>
                <p className="font-medium">
                  {serverConfig?.enabled && !serverConfig.using_fallback
                    ? "Custom Drive Connected"
                    : syncStatus?.configured
                    ? "Using Default Drive"
                    : "Not Connected"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {serverConfig?.enabled && !serverConfig.using_fallback
                    ? `Folder: ${serverConfig.folder_name || serverConfig.folder_id}`
                    : syncStatus?.configured
                    ? "Archives sync to the bot operator's Drive"
                    : "Connect Google Drive to enable backup"}
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              {serverConfig?.enabled && !serverConfig.using_fallback ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleTriggerSync}
                    disabled={triggerSync.isPending}
                  >
                    {triggerSync.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCw className="mr-2 h-4 w-4" />
                    )}
                    Sync Now
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleDisconnect}
                    disabled={disconnectDrive.isPending}
                  >
                    <Unlink className="mr-2 h-4 w-4" />
                    Disconnect
                  </Button>
                </>
              ) : oauthConfig?.configured ? (
                <Button onClick={handleConnectDrive} disabled={startOAuth.isPending}>
                  {startOAuth.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Link className="mr-2 h-4 w-4" />
                  )}
                  Connect Your Drive
                </Button>
              ) : syncStatus?.configured ? (
                <Badge variant="secondary">Using Fallback</Badge>
              ) : (
                <Badge variant="outline">OAuth Not Configured</Badge>
              )}
            </div>
          </div>

          {/* Server Sync Info */}
          {serverConfig?.last_sync && (
            <div className="text-sm text-muted-foreground">
              Last synced: {new Date(serverConfig.last_sync).toLocaleString()}
            </div>
          )}

          {/* Folder Selection Dialog */}
          {oauthConfig?.configured && !serverConfig?.enabled && (
            <Dialog open={selectedFolder !== null} onOpenChange={(open) => !open && setSelectedFolder(null)}>
              <DialogTrigger asChild>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => setSelectedFolder("root")}
                >
                  <Folder className="mr-2 h-4 w-4" />
                  Select Folder After Connecting
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-lg">
                <DialogHeader>
                  <DialogTitle>Select Archive Folder</DialogTitle>
                  <DialogDescription>
                    Choose where to store your archive summaries
                  </DialogDescription>
                </DialogHeader>

                {/* Breadcrumb */}
                <div className="flex items-center gap-1 text-sm overflow-x-auto py-2">
                  {folderPath.map((folder, index) => (
                    <div key={folder.id} className="flex items-center">
                      {index > 0 && <ChevronRight className="h-4 w-4 text-muted-foreground mx-1" />}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-auto py-1 px-2"
                        onClick={() => navigateBack(index)}
                      >
                        {folder.name}
                      </Button>
                    </div>
                  ))}
                </div>

                {/* Folder List */}
                <div className="border rounded-lg max-h-64 overflow-y-auto">
                  {foldersLoading ? (
                    <div className="flex items-center justify-center p-8">
                      <Loader2 className="h-6 w-6 animate-spin" />
                    </div>
                  ) : foldersData?.folders.length === 0 ? (
                    <div className="p-8 text-center text-muted-foreground">
                      No folders found
                    </div>
                  ) : (
                    foldersData?.folders.map((folder) => (
                      <div
                        key={folder.id}
                        className="flex items-center justify-between p-3 hover:bg-muted/50 border-b last:border-b-0"
                      >
                        <button
                          className="flex items-center gap-2 flex-1 text-left"
                          onClick={() => navigateToFolder(folder.id, folder.name)}
                        >
                          <Folder className="h-4 w-4 text-muted-foreground" />
                          <span>{folder.name}</span>
                        </button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleSelectFolder(folder.id, folder.name)}
                        >
                          Select
                        </Button>
                      </div>
                    ))
                  )}
                </div>

                <DialogFooter>
                  <Button
                    onClick={() =>
                      handleSelectFolder(
                        folderPath[folderPath.length - 1].id,
                        folderPath[folderPath.length - 1].name
                      )
                    }
                    disabled={configureSync.isPending}
                  >
                    {configureSync.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    Use Current Folder
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </CardContent>
      </Card>

      {/* Sync Status Details */}
      {syncStatus && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Sync Configuration
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Auto-sync on generation</p>
                <p className="font-medium">
                  {syncStatus.sync_on_generation ? "Enabled" : "Disabled"}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Sync frequency</p>
                <p className="font-medium capitalize">{syncStatus.sync_frequency.replace("_", " ")}</p>
              </div>
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Create server subfolders</p>
                <p className="font-medium">
                  {syncStatus.create_subfolders ? "Yes" : "No"}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Sources synced</p>
                <p className="font-medium">{syncStatus.sources_synced}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Drive Quota */}
      {driveStatus?.connected && driveStatus.quota && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="h-5 w-5" />
              Storage Quota
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Used</span>
                <span>
                  {(driveStatus.quota.usage / 1024 / 1024 / 1024).toFixed(2)} GB of{" "}
                  {(driveStatus.quota.limit / 1024 / 1024 / 1024).toFixed(0)} GB
                </span>
              </div>
              <Progress
                value={(driveStatus.quota.usage / driveStatus.quota.limit) * 100}
                className="h-2"
              />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
