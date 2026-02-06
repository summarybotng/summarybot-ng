import { useState, useMemo } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useGuild, useUpdateConfig, useSyncChannels } from "@/hooks/useGuilds";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Hash, Volume2, MessageSquare, RefreshCw, ChevronDown, Check } from "lucide-react";
import type { Channel } from "@/types";

const channelIcons = {
  text: Hash,
  voice: Volume2,
  forum: MessageSquare,
};

export function Channels() {
  const { id } = useParams<{ id: string }>();
  const { data: guild, isLoading } = useGuild(id || "");
  const updateConfig = useUpdateConfig(id || "");
  const syncChannels = useSyncChannels(id || "");
  const { toast } = useToast();
  
  const [openCategories, setOpenCategories] = useState<Set<string>>(new Set(["uncategorized"]));
  const [enabledChannels, setEnabledChannels] = useState<Set<string>>(new Set());
  const [hasChanges, setHasChanges] = useState(false);

  // Initialize enabled channels from guild config
  useMemo(() => {
    if (guild) {
      setEnabledChannels(new Set(guild.config.enabled_channels));
    }
  }, [guild]);

  // Group channels by category
  const channelsByCategory = useMemo(() => {
    if (!guild) return {};
    
    const grouped: Record<string, Channel[]> = {};
    
    guild.channels.forEach((channel) => {
      const category = channel.category || "uncategorized";
      if (!grouped[category]) {
        grouped[category] = [];
      }
      grouped[category].push(channel);
    });
    
    return grouped;
  }, [guild]);

  const toggleChannel = (channelId: string) => {
    setEnabledChannels((prev) => {
      const next = new Set(prev);
      if (next.has(channelId)) {
        next.delete(channelId);
      } else {
        next.add(channelId);
      }
      return next;
    });
    setHasChanges(true);
  };

  const toggleCategory = (category: string, enable: boolean) => {
    const channels = channelsByCategory[category] || [];
    setEnabledChannels((prev) => {
      const next = new Set(prev);
      channels.forEach((ch) => {
        if (enable) {
          next.add(ch.id);
        } else {
          next.delete(ch.id);
        }
      });
      return next;
    });
    setHasChanges(true);
  };

  const saveChanges = async () => {
    try {
      await updateConfig.mutateAsync({
        enabled_channels: Array.from(enabledChannels),
      });
      setHasChanges(false);
      toast({
        title: "Channels updated",
        description: "Your channel configuration has been saved.",
      });
    } catch (error: unknown) {
      const errorMessage = error instanceof Error 
        ? error.message 
        : (error as { error?: { message?: string } })?.error?.message || "Failed to update channel configuration.";
      console.error("Failed to save channels:", error);
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
    }
  };

  const handleSync = async () => {
    try {
      await syncChannels.mutateAsync();
      toast({
        title: "Channels synced",
        description: "Channel list has been refreshed from Discord.",
      });
    } catch (error: unknown) {
      const errorMessage = error instanceof Error 
        ? error.message 
        : (error as { error?: { message?: string } })?.error?.message || "Failed to sync channels.";
      console.error("Failed to sync channels:", error);
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
    }
  };

  if (isLoading) {
    return <ChannelsSkeleton />;
  }

  const categories = Object.keys(channelsByCategory).sort((a, b) => {
    if (a === "uncategorized") return 1;
    if (b === "uncategorized") return -1;
    return a.localeCompare(b);
  });

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold">Channels</h1>
          <p className="text-muted-foreground">
            Select which channels to include in summaries
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleSync}
            disabled={syncChannels.isPending}
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${syncChannels.isPending ? "animate-spin" : ""}`} />
            Sync Channels
          </Button>
          {hasChanges && (
            <Button onClick={saveChanges} disabled={updateConfig.isPending}>
              <Check className="mr-2 h-4 w-4" />
              Save Changes
            </Button>
          )}
        </div>
      </motion.div>

      <div className="space-y-4">
        {categories.map((category, categoryIndex) => {
          const channels = channelsByCategory[category];
          const enabledCount = channels.filter((ch) => enabledChannels.has(ch.id)).length;
          const allEnabled = enabledCount === channels.length;
          const isOpen = openCategories.has(category);

          return (
            <motion.div
              key={category}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: categoryIndex * 0.05 }}
            >
              <Card className="border-border/50">
                <Collapsible
                  open={isOpen}
                  onOpenChange={() => {
                    setOpenCategories((prev) => {
                      const next = new Set(prev);
                      if (next.has(category)) {
                        next.delete(category);
                      } else {
                        next.add(category);
                      }
                      return next;
                    });
                  }}
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CollapsibleTrigger className="flex items-center gap-2 hover:text-primary transition-colors">
                        <ChevronDown className={`h-4 w-4 transition-transform ${isOpen ? "" : "-rotate-90"}`} />
                        <CardTitle className="text-base font-semibold capitalize">
                          {category === "uncategorized" ? "No Category" : category}
                        </CardTitle>
                        <span className="text-sm text-muted-foreground">
                          ({enabledCount}/{channels.length})
                        </span>
                      </CollapsibleTrigger>
                      <div className="flex gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleCategory(category, true)}
                          disabled={allEnabled}
                        >
                          Enable All
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleCategory(category, false)}
                          disabled={enabledCount === 0}
                        >
                          Disable All
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CollapsibleContent>
                    <CardContent className="pt-0">
                      <div className="space-y-2">
                        {channels.map((channel) => {
                          const Icon = channelIcons[channel.type];
                          const isEnabled = enabledChannels.has(channel.id);

                          return (
                            <div
                              key={channel.id}
                              className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3"
                            >
                              <div className="flex items-center gap-3">
                                <Icon className="h-4 w-4 text-muted-foreground" />
                                <span className="font-medium">{channel.name}</span>
                              </div>
                              <Switch
                                checked={isEnabled}
                                onCheckedChange={() => toggleChannel(channel.id)}
                              />
                            </div>
                          );
                        })}
                      </div>
                    </CardContent>
                  </CollapsibleContent>
                </Collapsible>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

function ChannelsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between">
        <div>
          <Skeleton className="mb-2 h-8 w-28" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-10 w-32" />
      </div>
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <Card key={i} className="border-border/50">
            <CardHeader>
              <Skeleton className="h-6 w-40" />
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {[1, 2, 3].map((j) => (
                  <Skeleton key={j} className="h-12 w-full" />
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
