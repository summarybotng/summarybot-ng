import { useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useGuild } from "@/hooks/useGuilds";
import { useArchiveSources, type ArchiveSource } from "@/hooks/useArchive";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Hash,
  MessageCircle,
  Gamepad2,
  Slack,
  Search,
  CheckCircle2,
  XCircle,
  Calendar,
  Upload,
  ArrowRight,
  Layers,
} from "lucide-react";
import type { Channel } from "@/types";

type Platform = "all" | "discord" | "whatsapp" | "slack";

interface UnifiedSource {
  id: string;
  name: string;
  platform: "discord" | "whatsapp" | "slack";
  enabled: boolean;
  schedule?: string;
  lastActivity?: string;
  type?: string;
  isArchived?: boolean;
}

const platformConfig = {
  discord: {
    icon: Gamepad2,
    color: "text-indigo-500",
    bgColor: "bg-indigo-500/10",
    borderColor: "border-indigo-500/20",
    label: "Discord",
  },
  whatsapp: {
    icon: MessageCircle,
    color: "text-green-500",
    bgColor: "bg-green-500/10",
    borderColor: "border-green-500/20",
    label: "WhatsApp",
  },
  slack: {
    icon: Slack,
    color: "text-purple-500",
    bgColor: "bg-purple-500/10",
    borderColor: "border-purple-500/20",
    label: "Slack",
  },
};

export function Sources() {
  const { id: guildId } = useParams<{ id: string }>();
  const { data: guild, isLoading: guildLoading } = useGuild(guildId || "");
  const { data: archiveSources, isLoading: archiveLoading } = useArchiveSources(guildId || "");

  const [platformFilter, setPlatformFilter] = useState<Platform>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"name" | "platform" | "status">("platform");

  const isLoading = guildLoading || archiveLoading;

  // Transform data into unified source list
  const unifiedSources = useMemo((): UnifiedSource[] => {
    const sources: UnifiedSource[] = [];

    // Add Discord channels
    if (guild?.channels) {
      guild.channels.forEach((channel: Channel) => {
        sources.push({
          id: `discord-${channel.id}`,
          name: `#${channel.name}`,
          platform: "discord",
          enabled: guild.config.enabled_channels.includes(channel.id),
          type: channel.type,
        });
      });
    }

    // Add WhatsApp imports from archive sources
    if (archiveSources) {
      archiveSources.forEach((source: ArchiveSource) => {
        // Only show WhatsApp sources
        if (source.source_key.startsWith("whatsapp:")) {
          sources.push({
            id: `whatsapp-${source.source_key}`,
            name: source.source_key.replace("whatsapp:", "").replace(/_/g, " "),
            platform: "whatsapp",
            enabled: true,
            lastActivity: source.date_range?.end,
            isArchived: true,
          });
        }
      });
    }

    return sources;
  }, [guild, archiveSources]);

  // Apply filters and sorting
  const filteredSources = useMemo(() => {
    let result = unifiedSources;

    // Platform filter
    if (platformFilter !== "all") {
      result = result.filter((s) => s.platform === platformFilter);
    }

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter((s) => s.name.toLowerCase().includes(query));
    }

    // Sort
    result.sort((a, b) => {
      switch (sortBy) {
        case "name":
          return a.name.localeCompare(b.name);
        case "platform":
          return a.platform.localeCompare(b.platform) || a.name.localeCompare(b.name);
        case "status":
          return (b.enabled ? 1 : 0) - (a.enabled ? 1 : 0) || a.name.localeCompare(b.name);
        default:
          return 0;
      }
    });

    return result;
  }, [unifiedSources, platformFilter, searchQuery, sortBy]);

  // Platform counts
  const platformCounts = useMemo(() => {
    const counts: Record<Platform, number> = { all: 0, discord: 0, whatsapp: 0, slack: 0 };
    unifiedSources.forEach((s) => {
      counts[s.platform]++;
      counts.all++;
    });
    return counts;
  }, [unifiedSources]);

  if (isLoading) {
    return <SourcesSkeleton />;
  }

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Layers className="h-6 w-6" />
            Sources
          </h1>
          <p className="text-muted-foreground">
            All channels and imports across platforms
          </p>
        </div>
        <Button asChild variant="outline">
          <Link to={`/guilds/${guildId}/archive`}>
            <Upload className="mr-2 h-4 w-4" />
            Import WhatsApp
          </Link>
        </Button>
      </motion.div>

      {/* Platform filter buttons */}
      <div className="flex flex-wrap gap-2">
        {(["all", "discord", "whatsapp", "slack"] as const).map((platform) => {
          const count = platformCounts[platform];
          const isActive = platformFilter === platform;
          const config = platform === "all" ? null : platformConfig[platform];
          const Icon = config?.icon || Layers;

          return (
            <Button
              key={platform}
              variant={isActive ? "default" : "outline"}
              size="sm"
              onClick={() => setPlatformFilter(platform)}
              className={isActive ? "" : config?.bgColor}
            >
              <Icon className={`mr-1.5 h-4 w-4 ${!isActive && config?.color}`} />
              {platform === "all" ? "All" : config?.label}
              <Badge variant="secondary" className="ml-2 px-1.5 py-0 text-xs">
                {count}
              </Badge>
            </Button>
          );
        })}
      </div>

      {/* Search and sort controls */}
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search sources..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={sortBy} onValueChange={(v) => setSortBy(v as typeof sortBy)}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Sort by" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="platform">By Platform</SelectItem>
            <SelectItem value="name">By Name</SelectItem>
            <SelectItem value="status">By Status</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Sources list */}
      <Card className="border-border/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            {filteredSources.length} source{filteredSources.length !== 1 ? "s" : ""}
            {platformFilter !== "all" && ` (${platformConfig[platformFilter].label})`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {filteredSources.length === 0 ? (
            <div className="py-12 text-center">
              <Layers className="mx-auto mb-3 h-10 w-10 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">
                {searchQuery
                  ? "No sources match your search"
                  : platformFilter !== "all"
                    ? `No ${platformConfig[platformFilter].label} sources yet`
                    : "No sources configured"}
              </p>
              {platformFilter === "whatsapp" && (
                <Button asChild variant="link" className="mt-2">
                  <Link to={`/guilds/${guildId}/archive`}>
                    Import your first WhatsApp chat
                    <ArrowRight className="ml-1 h-4 w-4" />
                  </Link>
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              {filteredSources.map((source, index) => {
                const config = platformConfig[source.platform];
                const Icon = config.icon;

                return (
                  <motion.div
                    key={source.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.02 }}
                    className={`flex items-center justify-between rounded-lg px-4 py-3 ${config.bgColor} border ${config.borderColor}`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon className={`h-4 w-4 ${config.color}`} />
                      <span className="font-medium">{source.name}</span>
                      <Badge variant="outline" className={`${config.color} border-current/30`}>
                        {config.label}
                      </Badge>
                      {source.type && (
                        <Badge variant="secondary" className="text-xs">
                          {source.type}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      {source.isArchived && (
                        <Badge variant="secondary" className="text-xs">
                          <Calendar className="mr-1 h-3 w-3" />
                          Archived
                        </Badge>
                      )}
                      {source.schedule && (
                        <span className="text-xs text-muted-foreground">
                          {source.schedule}
                        </span>
                      )}
                      {source.enabled ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      ) : (
                        <XCircle className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick links */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link to={`/guilds/${guildId}/channels`}>
          <Card className="border-border/50 transition-all hover:border-primary/50 hover:shadow-md cursor-pointer">
            <CardContent className="flex items-center gap-4 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10">
                <Hash className="h-5 w-5 text-indigo-500" />
              </div>
              <div>
                <p className="font-medium">Configure Discord Channels</p>
                <p className="text-sm text-muted-foreground">
                  Enable or disable specific channels
                </p>
              </div>
            </CardContent>
          </Card>
        </Link>

        <Link to={`/guilds/${guildId}/archive`}>
          <Card className="border-border/50 transition-all hover:border-primary/50 hover:shadow-md cursor-pointer">
            <CardContent className="flex items-center gap-4 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-500/10">
                <MessageCircle className="h-5 w-5 text-green-500" />
              </div>
              <div>
                <p className="font-medium">Import WhatsApp Chat</p>
                <p className="text-sm text-muted-foreground">
                  Upload a WhatsApp export zip file
                </p>
              </div>
            </CardContent>
          </Card>
        </Link>

        <Link to="/slack">
          <Card className="border-border/50 transition-all hover:border-primary/50 hover:shadow-md cursor-pointer">
            <CardContent className="flex items-center gap-4 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-500/10">
                <Slack className="h-5 w-5 text-purple-500" />
              </div>
              <div>
                <p className="font-medium">Connect Slack Workspace</p>
                <p className="text-sm text-muted-foreground">
                  Link your Slack workspace
                </p>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  );
}

function SourcesSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between">
        <div>
          <Skeleton className="mb-2 h-8 w-28" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-10 w-36" />
      </div>
      <div className="flex gap-2">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-9 w-24" />
        ))}
      </div>
      <Card className="border-border/50">
        <CardHeader>
          <Skeleton className="h-5 w-32" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
