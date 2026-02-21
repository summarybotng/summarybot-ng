import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useGuilds } from "@/hooks/useGuilds";
import { useDefaultPrompts, type DefaultPrompt } from "@/hooks/usePrompts";
import { Header } from "@/components/layout/Header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Users, FileText, AlertCircle, CheckCircle2, Settings, GitBranch, Eye, MessageSquare, Gavel, MessagesSquare } from "lucide-react";
import type { Guild } from "@/types";

function GuildCard({ guild, index }: { guild: Guild; index: number }) {
  const statusConfig = {
    configured: { label: "Configured", variant: "default" as const, icon: CheckCircle2 },
    needs_setup: { label: "Needs Setup", variant: "secondary" as const, icon: Settings },
    inactive: { label: "Inactive", variant: "outline" as const, icon: AlertCircle },
  };

  const status = statusConfig[guild.config_status];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.05 }}
    >
      <Link to={`/guilds/${guild.id}`}>
        <Card className="group h-full cursor-pointer border-border/50 bg-card/50 transition-all hover:border-primary/50 hover:bg-card hover:shadow-lg">
          <CardContent className="p-5">
            <div className="mb-4 flex items-start justify-between">
              <Avatar className="h-14 w-14 rounded-xl">
                <AvatarImage src={guild.icon_url || ""} alt={guild.name} />
                <AvatarFallback className="rounded-xl bg-primary/20 text-lg font-semibold text-primary">
                  {guild.name.slice(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <Badge variant={status.variant} className="text-xs">
                <status.icon className="mr-1 h-3 w-3" />
                {status.label}
              </Badge>
            </div>

            <h3 className="mb-3 truncate text-lg font-semibold group-hover:text-primary transition-colors">
              {guild.name}
            </h3>

            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <Users className="h-4 w-4" />
                <span>{guild.member_count.toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <FileText className="h-4 w-4" />
                <span>{guild.summary_count} summaries</span>
              </div>
            </div>

            {guild.last_summary_at && (
              <p className="mt-3 text-xs text-muted-foreground">
                Last summary: {new Date(guild.last_summary_at).toLocaleDateString()}
              </p>
            )}
          </CardContent>
        </Card>
      </Link>
    </motion.div>
  );
}

function GuildSkeleton() {
  return (
    <Card className="border-border/50">
      <CardContent className="p-5">
        <div className="mb-4 flex items-start justify-between">
          <Skeleton className="h-14 w-14 rounded-xl" />
          <Skeleton className="h-5 w-20" />
        </div>
        <Skeleton className="mb-3 h-6 w-3/4" />
        <div className="flex gap-4">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-24" />
        </div>
      </CardContent>
    </Card>
  );
}

// Icon mapping for prompt categories
const PROMPT_ICONS: Record<string, typeof FileText> = {
  default: FileText,
  discussion: MessagesSquare,
  meeting: MessageSquare,
  moderation: Gavel,
};

function DefaultPromptsCard() {
  const { data: prompts, isLoading } = useDefaultPrompts();
  const [selectedPrompt, setSelectedPrompt] = useState<DefaultPrompt | null>(null);

  if (isLoading) {
    return (
      <Card className="border-border/50 bg-card/50">
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Skeleton className="h-9 w-24" />
            <Skeleton className="h-9 w-24" />
            <Skeleton className="h-9 w-24" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card className="border-border/50 bg-card/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <GitBranch className="h-5 w-5" />
            Default Prompts
          </CardTitle>
          <CardDescription>
            View the built-in prompts that drive summary generation
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {prompts?.map((prompt) => {
              const Icon = PROMPT_ICONS[prompt.category] || FileText;
              return (
                <Button
                  key={prompt.name}
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedPrompt(prompt)}
                  className="gap-2"
                >
                  <Icon className="h-4 w-4" />
                  <span className="capitalize">{prompt.name}</span>
                  <Eye className="h-3 w-3 text-muted-foreground" />
                </Button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Prompt Viewer Dialog */}
      <Dialog open={!!selectedPrompt} onOpenChange={(open) => !open && setSelectedPrompt(null)}>
        <DialogContent className="max-w-3xl max-h-[80vh]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 capitalize">
              {selectedPrompt && (
                <>
                  {(() => {
                    const Icon = PROMPT_ICONS[selectedPrompt.category] || FileText;
                    return <Icon className="h-5 w-5" />;
                  })()}
                  {selectedPrompt.name} Prompt
                </>
              )}
            </DialogTitle>
            <DialogDescription>
              {selectedPrompt?.description}
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh] pr-4">
            <pre className="text-sm bg-muted/50 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap font-mono">
              {selectedPrompt?.content}
            </pre>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function Guilds() {
  const { data: guilds, isLoading, error } = useGuilds();

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container py-8">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="mb-2 text-3xl font-bold">Your Servers</h1>
          <p className="text-muted-foreground">
            Select a server to configure SummaryBot
          </p>
        </motion.div>

        {/* Default Prompts Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="mb-8"
        >
          <DefaultPromptsCard />
        </motion.div>

        {error && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <AlertCircle className="mb-4 h-12 w-12 text-destructive" />
            <h2 className="mb-2 text-xl font-semibold">Failed to load servers</h2>
            <p className="text-muted-foreground">Please try refreshing the page</p>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {isLoading
            ? Array.from({ length: 6 }).map((_, i) => <GuildSkeleton key={i} />)
            : guilds?.map((guild, index) => (
                <GuildCard key={guild.id} guild={guild} index={index} />
              ))}
        </div>

        {!isLoading && guilds?.length === 0 && (
          <div className="py-20 text-center">
            <p className="text-lg text-muted-foreground">
              No servers found. Make sure SummaryBot is added to your Discord servers.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
