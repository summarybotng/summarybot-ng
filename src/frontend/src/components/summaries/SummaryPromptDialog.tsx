import { useState } from "react";
import { useSummaryPrompt } from "@/hooks/useSummaries";
import { useSummary } from "@/hooks/useSummaries";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { FileText, Bot, MessageSquare, Copy, Check, ExternalLink, ChevronDown, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { PromptSource } from "@/types";

interface SummaryPromptDialogProps {
  guildId: string;
  summaryId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SummaryPromptDialog({
  guildId,
  summaryId,
  open,
  onOpenChange,
}: SummaryPromptDialogProps) {
  const { data: promptData, isLoading: promptLoading } = useSummaryPrompt(guildId, summaryId, open);
  const { data: summaryDetail, isLoading: summaryLoading } = useSummary(guildId, summaryId);
  const [copiedTab, setCopiedTab] = useState<string | null>(null);

  const isLoading = promptLoading || summaryLoading;
  const promptSource = summaryDetail?.metadata?.prompt_source;

  const handleCopy = async (content: string | null, tab: string) => {
    if (!content) return;
    await navigator.clipboard.writeText(content);
    setCopiedTab(tab);
    setTimeout(() => setCopiedTab(null), 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Generation Details
            {promptData?.prompt_template_id && (
              <Badge variant="secondary" className="ml-2">
                Custom template: {promptData.prompt_template_id}
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-4 py-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-48 w-full" />
          </div>
        ) : (
          <Tabs defaultValue="source" className="mt-2">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="source" className="text-xs sm:text-sm">
                <FileText className="mr-1.5 h-3.5 w-3.5 hidden sm:inline" />
                Source
              </TabsTrigger>
              <TabsTrigger value="system" className="text-xs sm:text-sm">
                <Bot className="mr-1.5 h-3.5 w-3.5 hidden sm:inline" />
                System
              </TabsTrigger>
              <TabsTrigger value="user" className="text-xs sm:text-sm">
                <MessageSquare className="mr-1.5 h-3.5 w-3.5 hidden sm:inline" />
                User
              </TabsTrigger>
            </TabsList>

            <TabsContent value="source" className="mt-4">
              <PromptTabContent
                title="Original Messages"
                description="The raw messages that were summarized"
                content={promptData?.source_content}
                isCode={false}
                onCopy={() => handleCopy(promptData?.source_content ?? null, "source")}
                copied={copiedTab === "source"}
              />
            </TabsContent>

            <TabsContent value="system" className="mt-4 space-y-4">
              {promptSource && <PromptSourceSection promptSource={promptSource} />}
              <PromptTabContent
                title="System Prompt"
                description="Instructions that define how the AI should summarize"
                content={promptData?.prompt_system}
                isCode={true}
                onCopy={() => handleCopy(promptData?.prompt_system ?? null, "system")}
                copied={copiedTab === "system"}
              />
            </TabsContent>

            <TabsContent value="user" className="mt-4">
              <PromptTabContent
                title="User Prompt"
                description="The formatted messages sent to the AI"
                content={promptData?.prompt_user}
                isCode={true}
                onCopy={() => handleCopy(promptData?.prompt_user ?? null, "user")}
                copied={copiedTab === "user"}
              />
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PromptSourceSection({ promptSource }: { promptSource: PromptSource }) {
  const [triedPathsOpen, setTriedPathsOpen] = useState(false);

  const getSourceBadgeVariant = (source: PromptSource["source"]) => {
    switch (source) {
      case "custom":
        return "bg-green-500/15 text-green-400 border-green-500/30";
      case "default":
        return "bg-blue-500/15 text-blue-400 border-blue-500/30";
      case "cached":
        return "bg-yellow-500/15 text-yellow-400 border-yellow-500/30";
      case "fallback":
        return "bg-muted text-muted-foreground border-border";
      default:
        return "";
    }
  };

  return (
    <div className="rounded-md border bg-muted/30 p-4">
      <h4 className="mb-3 text-sm font-medium">Prompt Source</h4>
      <div className="space-y-2 text-sm font-mono">
        {/* Source */}
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">├─ Source:</span>
          <Badge variant="outline" className={getSourceBadgeVariant(promptSource.source)}>
            {promptSource.source}
          </Badge>
          {promptSource.is_stale && (
            <Badge variant="outline" className="bg-yellow-500/15 text-yellow-400 border-yellow-500/30">
              <AlertTriangle className="mr-1 h-3 w-3" />
              Stale Cache
            </Badge>
          )}
        </div>

        {/* File Path */}
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground">├─ File:</span>
          <span className="break-all">
            {promptSource.file_path || "Hardcoded fallback"}
          </span>
        </div>

        {/* GitHub Link */}
        {promptSource.github_file_url && (
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">├─ GitHub:</span>
            <a
              href={promptSource.github_file_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              View on GitHub
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        )}

        {/* Repo URL */}
        {promptSource.repo_url && (
          <div className="flex items-start gap-2">
            <span className="text-muted-foreground">├─ Repo:</span>
            <a
              href={promptSource.repo_url}
              target="_blank"
              rel="noopener noreferrer"
              className="break-all text-primary hover:underline"
            >
              {promptSource.repo_url}
            </a>
          </div>
        )}

        {/* Tried Paths */}
        {promptSource.tried_paths && promptSource.tried_paths.length > 0 && (
          <Collapsible open={triedPathsOpen} onOpenChange={setTriedPathsOpen}>
            <CollapsibleTrigger className="flex items-center gap-2 hover:text-foreground">
              <span className="text-muted-foreground">├─ Tried:</span>
              <span className="text-xs text-muted-foreground">
                {promptSource.tried_paths.length} path{promptSource.tried_paths.length > 1 ? "s" : ""}
              </span>
              <ChevronDown
                className={`h-3 w-3 text-muted-foreground transition-transform ${
                  triedPathsOpen ? "rotate-180" : ""
                }`}
              />
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-1 pl-6">
              <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                {promptSource.tried_paths.map((path, index) => (
                  <span key={index} className="flex items-center">
                    <span className="rounded bg-muted px-1.5 py-0.5">{path}</span>
                    {index < promptSource.tried_paths.length - 1 && (
                      <span className="mx-1">→</span>
                    )}
                  </span>
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Version */}
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">└─ Version:</span>
          <span>{promptSource.version}</span>
        </div>
      </div>
    </div>
  );
}

function PromptTabContent({
  title,
  description,
  content,
  isCode,
  onCopy,
  copied,
}: {
  title: string;
  description: string;
  content: string | null | undefined;
  isCode: boolean;
  onCopy: () => void;
  copied: boolean;
}) {
  const hasContent = content && content.trim().length > 0;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-medium">{title}</h4>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        {hasContent && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onCopy}
            className="h-8 px-2"
          >
            {copied ? (
              <>
                <Check className="mr-1 h-3.5 w-3.5" />
                Copied
              </>
            ) : (
              <>
                <Copy className="mr-1 h-3.5 w-3.5" />
                Copy
              </>
            )}
          </Button>
        )}
      </div>

      <ScrollArea className="h-[300px] rounded-md border bg-muted/30">
        {hasContent ? (
          <div className={`p-4 ${isCode ? "font-mono text-xs" : "text-sm"}`}>
            <pre className="whitespace-pre-wrap break-words">{content}</pre>
          </div>
        ) : (
          <div className="flex h-full min-h-[200px] items-center justify-center text-muted-foreground">
            No data available
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
