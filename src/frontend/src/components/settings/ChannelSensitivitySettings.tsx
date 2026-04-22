/**
 * ADR-046: Channel Sensitivity Settings Component
 *
 * Allows admins to configure which channels are marked as sensitive.
 * Summaries from sensitive channels require admin role to view.
 */

import { useState, useMemo, useEffect } from "react";
import { motion } from "framer-motion";
import {
  useChannelSensitivityConfig,
  useUpdateChannelSensitivity,
} from "@/hooks/useChannelSensitivity";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  AlertTriangle,
  ChevronDown,
  Hash,
  Loader2,
  Lock,
  Save,
  Search,
  Shield,
  X,
} from "lucide-react";
import type { Channel, Category, ChannelSensitivityConfig } from "@/types";

interface ChannelSensitivitySettingsProps {
  guildId: string;
  channels: Channel[];
  categories: Category[];
  animationDelay?: number;
}

export function ChannelSensitivitySettings({
  guildId,
  channels,
  categories,
  animationDelay = 0.3,
}: ChannelSensitivitySettingsProps) {
  const { data: config, isLoading } = useChannelSensitivityConfig(guildId);
  const updateConfig = useUpdateChannelSensitivity(guildId);
  const { toast } = useToast();

  const [localConfig, setLocalConfig] = useState<ChannelSensitivityConfig>({
    sensitive_channels: [],
    sensitive_categories: [],
    auto_mark_private_sensitive: true,
  });
  const [hasChanges, setHasChanges] = useState(false);
  const [channelSearch, setChannelSearch] = useState("");
  const [isChannelSelectorOpen, setIsChannelSelectorOpen] = useState(false);

  // Sync local state with fetched config
  useEffect(() => {
    if (config) {
      setLocalConfig(config);
      setHasChanges(false);
    }
  }, [config]);

  // Filter text channels for selection
  const textChannels = useMemo(
    () => channels.filter((c) => c.type === "text"),
    [channels]
  );

  const filteredChannels = useMemo(
    () =>
      textChannels.filter((c) =>
        c.name.toLowerCase().includes(channelSearch.toLowerCase())
      ),
    [textChannels, channelSearch]
  );

  // Group channels by category for display
  const channelsByCategory = useMemo(() => {
    const grouped: Record<string, Channel[]> = {};
    textChannels.forEach((channel) => {
      const category = channel.category || "uncategorized";
      if (!grouped[category]) {
        grouped[category] = [];
      }
      grouped[category].push(channel);
    });
    return grouped;
  }, [textChannels]);

  // Get channel name by ID
  const getChannelName = (channelId: string): string => {
    const channel = channels.find((c) => c.id === channelId);
    return channel ? channel.name : channelId;
  };

  // Get category name by ID
  const getCategoryName = (categoryId: string): string => {
    const category = categories.find((c) => c.id === categoryId);
    return category ? category.name : categoryId;
  };

  const handleToggleAutoPrivate = (checked: boolean) => {
    setLocalConfig((prev) => ({
      ...prev,
      auto_mark_private_sensitive: checked,
    }));
    setHasChanges(true);
  };

  const handleToggleChannel = (channelId: string, checked: boolean) => {
    setLocalConfig((prev) => ({
      ...prev,
      sensitive_channels: checked
        ? [...prev.sensitive_channels, channelId]
        : prev.sensitive_channels.filter((id) => id !== channelId),
    }));
    setHasChanges(true);
  };

  const handleRemoveChannel = (channelId: string) => {
    setLocalConfig((prev) => ({
      ...prev,
      sensitive_channels: prev.sensitive_channels.filter((id) => id !== channelId),
    }));
    setHasChanges(true);
  };

  const handleToggleCategory = (categoryId: string, checked: boolean) => {
    setLocalConfig((prev) => ({
      ...prev,
      sensitive_categories: checked
        ? [...prev.sensitive_categories, categoryId]
        : prev.sensitive_categories.filter((id) => id !== categoryId),
    }));
    setHasChanges(true);
  };

  const handleSave = async () => {
    try {
      await updateConfig.mutateAsync(localConfig);
      setHasChanges(false);
      toast({
        title: "Settings saved",
        description: "Channel sensitivity configuration has been updated.",
      });
    } catch (error) {
      console.error("Failed to save channel sensitivity config:", error);
      toast({
        title: "Error",
        description: "Failed to save channel sensitivity settings.",
        variant: "destructive",
      });
    }
  };

  if (isLoading) {
    return <ChannelSensitivitySkeleton />;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: animationDelay }}
    >
      <Card className="border-border/50">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              <CardTitle>Channel Privacy</CardTitle>
            </div>
            {hasChanges && (
              <Button
                size="sm"
                onClick={handleSave}
                disabled={updateConfig.isPending}
              >
                {updateConfig.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Save Changes
              </Button>
            )}
          </div>
          <CardDescription>
            Mark channels as sensitive to restrict summary visibility to admins only.
            Summaries containing content from sensitive channels will not be visible
            to regular guild members.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Privacy Notice */}
          <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-amber-500 shrink-0" />
            <div className="text-sm">
              <p className="font-medium text-amber-500">Privacy Notice</p>
              <p className="text-muted-foreground mt-1">
                By default, summaries are visible to all guild members who can access
                the dashboard. Use these settings to protect sensitive conversations.
              </p>
            </div>
          </div>

          {/* Auto-mark private channels */}
          <div className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3">
            <div className="flex items-center gap-3">
              <Lock className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="font-medium">Auto-mark private channels as sensitive</p>
                <p className="text-sm text-muted-foreground">
                  Automatically treat channels not visible to @everyone as sensitive
                </p>
              </div>
            </div>
            <Switch
              checked={localConfig.auto_mark_private_sensitive}
              onCheckedChange={handleToggleAutoPrivate}
            />
          </div>

          {/* Sensitive Categories */}
          <div className="space-y-3">
            <label className="text-sm font-medium">Sensitive Categories</label>
            <p className="text-xs text-muted-foreground">
              All channels in selected categories will be treated as sensitive
            </p>
            <div className="space-y-2">
              {categories.map((category) => (
                <div
                  key={category.id}
                  className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3"
                >
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id={`category-${category.id}`}
                      checked={localConfig.sensitive_categories.includes(category.id)}
                      onCheckedChange={(checked) =>
                        handleToggleCategory(category.id, checked as boolean)
                      }
                    />
                    <label
                      htmlFor={`category-${category.id}`}
                      className="text-sm cursor-pointer"
                    >
                      {category.name}
                    </label>
                    <span className="text-xs text-muted-foreground">
                      ({category.channel_count} channels)
                    </span>
                  </div>
                  {localConfig.sensitive_categories.includes(category.id) && (
                    <Badge variant="secondary" className="text-xs">
                      <Lock className="mr-1 h-3 w-3" />
                      Sensitive
                    </Badge>
                  )}
                </div>
              ))}
              {categories.length === 0 && (
                <p className="text-sm text-muted-foreground py-2">
                  No categories found in this server
                </p>
              )}
            </div>
          </div>

          {/* Sensitive Channels */}
          <div className="space-y-3">
            <label className="text-sm font-medium">Sensitive Channels</label>
            <p className="text-xs text-muted-foreground">
              Manually mark individual channels as sensitive
            </p>

            {/* Currently marked channels */}
            {localConfig.sensitive_channels.length > 0 && (
              <div className="flex flex-wrap gap-2 rounded-lg border border-border/50 p-3">
                {localConfig.sensitive_channels.map((channelId) => (
                  <Badge
                    key={channelId}
                    variant="secondary"
                    className="flex items-center gap-1 pr-1"
                  >
                    <Hash className="h-3 w-3" />
                    {getChannelName(channelId)}
                    <button
                      onClick={() => handleRemoveChannel(channelId)}
                      className="ml-1 rounded-full p-0.5 hover:bg-muted"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}

            {/* Channel selector */}
            <Collapsible
              open={isChannelSelectorOpen}
              onOpenChange={setIsChannelSelectorOpen}
            >
              <CollapsibleTrigger asChild>
                <Button variant="outline" className="w-full justify-between">
                  <span className="flex items-center gap-2">
                    <Hash className="h-4 w-4" />
                    {localConfig.sensitive_channels.length === 0
                      ? "Select channels to mark as sensitive"
                      : `${localConfig.sensitive_channels.length} channel(s) marked`}
                  </span>
                  <ChevronDown
                    className={`h-4 w-4 transition-transform ${
                      isChannelSelectorOpen ? "rotate-180" : ""
                    }`}
                  />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="pt-3">
                <div className="space-y-3 rounded-lg border border-border/50 p-3">
                  {/* Search */}
                  <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search channels..."
                      value={channelSearch}
                      onChange={(e) => setChannelSearch(e.target.value)}
                      className="pl-8"
                    />
                  </div>

                  {/* Channel list grouped by category */}
                  <div className="max-h-60 overflow-y-auto space-y-4">
                    {Object.entries(channelsByCategory)
                      .sort(([a], [b]) => {
                        if (a === "uncategorized") return 1;
                        if (b === "uncategorized") return -1;
                        return a.localeCompare(b);
                      })
                      .map(([category, categoryChannels]) => {
                        const filteredCategoryChannels = categoryChannels.filter((c) =>
                          c.name.toLowerCase().includes(channelSearch.toLowerCase())
                        );

                        if (filteredCategoryChannels.length === 0) return null;

                        return (
                          <div key={category} className="space-y-2">
                            <p className="text-xs font-medium text-muted-foreground uppercase">
                              {category === "uncategorized" ? "No Category" : category}
                            </p>
                            {filteredCategoryChannels.map((channel) => {
                              const isInSensitiveCategory =
                                localConfig.sensitive_categories.some(
                                  (catId) =>
                                    categories.find((c) => c.id === catId)?.name ===
                                    channel.category
                                );

                              return (
                                <div
                                  key={channel.id}
                                  className="flex items-center gap-2"
                                >
                                  <Checkbox
                                    id={`channel-${channel.id}`}
                                    checked={localConfig.sensitive_channels.includes(
                                      channel.id
                                    )}
                                    onCheckedChange={(checked) =>
                                      handleToggleChannel(channel.id, checked as boolean)
                                    }
                                    disabled={isInSensitiveCategory}
                                  />
                                  <label
                                    htmlFor={`channel-${channel.id}`}
                                    className={`text-sm cursor-pointer flex items-center gap-1 ${
                                      isInSensitiveCategory
                                        ? "text-muted-foreground"
                                        : ""
                                    }`}
                                  >
                                    <Hash className="h-3 w-3" />
                                    {channel.name}
                                  </label>
                                  {isInSensitiveCategory && (
                                    <span className="text-xs text-muted-foreground">
                                      (via category)
                                    </span>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        );
                      })}
                    {filteredChannels.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center py-4">
                        {channelSearch
                          ? `No channels match "${channelSearch}"`
                          : "No text channels available"}
                      </p>
                    )}
                  </div>
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>

          {/* Summary of sensitive channels */}
          {(localConfig.sensitive_channels.length > 0 ||
            localConfig.sensitive_categories.length > 0 ||
            localConfig.auto_mark_private_sensitive) && (
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 space-y-2">
              <p className="text-sm font-medium">Effective Protection</p>
              <ul className="text-sm text-muted-foreground space-y-1">
                {localConfig.auto_mark_private_sensitive && (
                  <li className="flex items-center gap-2">
                    <Lock className="h-3 w-3" />
                    All private channels (not visible to @everyone)
                  </li>
                )}
                {localConfig.sensitive_categories.length > 0 && (
                  <li className="flex items-center gap-2">
                    <Shield className="h-3 w-3" />
                    {localConfig.sensitive_categories.length} categor
                    {localConfig.sensitive_categories.length === 1 ? "y" : "ies"} (
                    {localConfig.sensitive_categories
                      .map((id) => getCategoryName(id))
                      .join(", ")}
                    )
                  </li>
                )}
                {localConfig.sensitive_channels.length > 0 && (
                  <li className="flex items-center gap-2">
                    <Hash className="h-3 w-3" />
                    {localConfig.sensitive_channels.length} individual channel
                    {localConfig.sensitive_channels.length === 1 ? "" : "s"}
                  </li>
                )}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function ChannelSensitivitySkeleton() {
  return (
    <Card className="border-border/50">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Skeleton className="h-5 w-5" />
          <Skeleton className="h-6 w-36" />
        </div>
        <Skeleton className="h-4 w-full mt-2" />
        <Skeleton className="h-4 w-3/4" />
      </CardHeader>
      <CardContent className="space-y-6">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
      </CardContent>
    </Card>
  );
}

export default ChannelSensitivitySettings;
