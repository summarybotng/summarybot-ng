import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useGuilds } from "@/hooks/useGuilds";
import { Header } from "@/components/layout/Header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { Users, FileText, AlertCircle, CheckCircle2, Settings } from "lucide-react";
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
