import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useGuild } from "@/hooks/useGuilds";
import { useErrorCounts } from "@/hooks/useErrors";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { FileText, Calendar, Hash, Sparkles, ArrowRight, Clock, AlertTriangle } from "lucide-react";

export function GuildDashboard() {
  const { id } = useParams<{ id: string }>();
  const { data: guild, isLoading } = useGuild(id || "");
  const { data: errorCounts } = useErrorCounts(id || "", 24);
  if (isLoading) {
    return <DashboardSkeleton />;
  }

  if (!guild) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Guild not found</p>
      </div>
    );
  }

  const stats = [
    {
      label: "Total Summaries",
      value: guild.stats.total_summaries,
      icon: FileText,
      color: "text-primary",
      bg: "bg-primary/10",
    },
    {
      label: "This Week",
      value: guild.stats.summaries_this_week,
      icon: Calendar,
      color: "text-discord-green",
      bg: "bg-discord-green/10",
    },
    {
      label: "Active Schedules",
      value: guild.stats.active_schedules,
      icon: Clock,
      color: "text-discord-yellow",
      bg: "bg-discord-yellow/10",
    },
    {
      label: "Enabled Channels",
      value: guild.config.enabled_channels.length,
      icon: Hash,
      color: "text-info",
      bg: "bg-info/10",
    },
  ];

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold">Overview</h1>
          <p className="text-muted-foreground">
            Dashboard for {guild.name}
          </p>
        </div>
        <Button asChild>
          <Link to={`/guilds/${id}/summaries`}>
            <Sparkles className="mr-2 h-4 w-4" />
            Generate Summary
          </Link>
        </Button>
      </motion.div>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat, index) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Card className="border-border/50">
              <CardContent className="p-5">
                <div className="flex items-center gap-4">
                  <div className={`flex h-12 w-12 items-center justify-center rounded-lg ${stat.bg}`}>
                    <stat.icon className={`h-6 w-6 ${stat.color}`} />
                  </div>
                  <div>
                    <p className="text-2xl font-bold">{stat.value}</p>
                    <p className="text-sm text-muted-foreground">{stat.label}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Error Stats */}
      {errorCounts && errorCounts.total > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
        >
          <Card className="border-border/50 border-orange-500/20 bg-orange-500/5">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-orange-500" />
                Errors (Last 24h)
              </CardTitle>
              <Button variant="ghost" size="sm" asChild>
                <Link to={`/guilds/${id}/errors`}>
                  View All
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {Object.entries(errorCounts.counts).map(([type, count]) => (
                  <Badge
                    key={type}
                    variant="outline"
                    className="border-orange-500/30 bg-orange-500/10"
                  >
                    {type.replace(/_/g, " ")}: {count}
                  </Badge>
                ))}
                <Badge variant="destructive" className="ml-auto">
                  {errorCounts.total} total
                </Badge>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Quick Actions */}
      <div className="grid gap-4 lg:grid-cols-2">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
        >
          <Card className="border-border/50">
            <CardHeader>
              <CardTitle className="text-lg">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Link
                to={`/guilds/${id}/channels`}
                className="flex items-center justify-between rounded-lg bg-muted/50 p-4 transition-colors hover:bg-muted"
              >
                <div className="flex items-center gap-3">
                  <Hash className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium">Configure Channels</p>
                    <p className="text-sm text-muted-foreground">
                      Select which channels to summarize
                    </p>
                  </div>
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground" />
              </Link>

              <Link
                to={`/guilds/${id}/schedules`}
                className="flex items-center justify-between rounded-lg bg-muted/50 p-4 transition-colors hover:bg-muted"
              >
                <div className="flex items-center gap-3">
                  <Calendar className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium">Manage Schedules</p>
                    <p className="text-sm text-muted-foreground">
                      Set up automated summary schedules
                    </p>
                  </div>
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground" />
              </Link>
            </CardContent>
          </Card>
        </motion.div>

        {/* Recent Activity */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.4 }}
        >
          <Card className="border-border/50">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg">Recent Summaries</CardTitle>
              <Button variant="ghost" size="sm" asChild>
                <Link to={`/guilds/${id}/summaries`}>
                  View All
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent>
              {guild.stats.total_summaries === 0 ? (
                <div className="py-8 text-center">
                  <FileText className="mx-auto mb-3 h-10 w-10 text-muted-foreground/50" />
                  <p className="text-sm text-muted-foreground">
                    No summaries yet. Generate your first one!
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    Last summary:{" "}
                    {guild.stats.last_summary_at
                      ? new Date(guild.stats.last_summary_at).toLocaleString()
                      : "Never"}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between">
        <div>
          <Skeleton className="mb-2 h-8 w-32" />
          <Skeleton className="h-4 w-48" />
        </div>
        <Skeleton className="h-10 w-36" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} className="border-border/50">
            <CardContent className="p-5">
              <div className="flex items-center gap-4">
                <Skeleton className="h-12 w-12 rounded-lg" />
                <div>
                  <Skeleton className="mb-1 h-7 w-12" />
                  <Skeleton className="h-4 w-24" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
