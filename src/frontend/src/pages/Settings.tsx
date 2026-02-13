import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { formatDistanceToNow } from "date-fns";
import { useGuild, useUpdateConfig } from "@/hooks/useGuilds";
import { useHealth } from "@/hooks/useHealth";
import { useTimezone, TIMEZONE_OPTIONS } from "@/contexts/TimezoneContext";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Save, Loader2, Server, Globe } from "lucide-react";
import type { SummaryOptions } from "@/types";

export function Settings() {
  const { id } = useParams<{ id: string }>();
  const { data: guild, isLoading } = useGuild(id || "");
  const { data: health } = useHealth();
  const updateConfig = useUpdateConfig(id || "");
  const { toast } = useToast();
  const { timezone, setTimezone } = useTimezone();

  const [options, setOptions] = useState<SummaryOptions>({
    summary_length: "detailed",
    perspective: "general",
    include_action_items: true,
    include_technical_terms: true,
  });
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    if (guild?.config.default_options) {
      setOptions(guild.config.default_options);
    }
  }, [guild]);

  const handleSave = async () => {
    try {
      await updateConfig.mutateAsync({
        default_options: options,
      });
      setHasChanges(false);
      toast({
        title: "Settings saved",
        description: "Your default options have been updated.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to save settings.",
        variant: "destructive",
      });
    }
  };

  const updateOption = <K extends keyof SummaryOptions>(key: K, value: SummaryOptions[K]) => {
    setOptions((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  if (isLoading) {
    return <SettingsSkeleton />;
  }

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-muted-foreground">
            Configure default options for {guild?.name}
          </p>
        </div>
        {hasChanges && (
          <Button onClick={handleSave} disabled={updateConfig.isPending}>
            {updateConfig.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            Save Changes
          </Button>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle>Default Summary Options</CardTitle>
            <CardDescription>
              These settings will be used as defaults when generating summaries
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium">Summary Length</label>
                <Select
                  value={options.summary_length}
                  onValueChange={(v) => updateOption("summary_length", v as SummaryOptions["summary_length"])}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="brief">
                      <div>
                        <p>Brief</p>
                        <p className="text-xs text-muted-foreground">Quick highlights only</p>
                      </div>
                    </SelectItem>
                    <SelectItem value="detailed">
                      <div>
                        <p>Detailed</p>
                        <p className="text-xs text-muted-foreground">Comprehensive overview</p>
                      </div>
                    </SelectItem>
                    <SelectItem value="comprehensive">
                      <div>
                        <p>Comprehensive</p>
                        <p className="text-xs text-muted-foreground">Full in-depth analysis</p>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Perspective</label>
                <Select
                  value={options.perspective}
                  onValueChange={(v) => updateOption("perspective", v as SummaryOptions["perspective"])}
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
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3">
                <div>
                  <p className="font-medium">Include Action Items</p>
                  <p className="text-sm text-muted-foreground">
                    Extract and list action items from conversations
                  </p>
                </div>
                <Switch
                  checked={options.include_action_items}
                  onCheckedChange={(v) => updateOption("include_action_items", v)}
                />
              </div>

              <div className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3">
                <div>
                  <p className="font-medium">Include Technical Terms</p>
                  <p className="text-sm text-muted-foreground">
                    Extract and define technical terminology
                  </p>
                </div>
                <Switch
                  checked={options.include_technical_terms}
                  onCheckedChange={(v) => updateOption("include_technical_terms", v)}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Timezone Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5" />
              Timezone
            </CardTitle>
            <CardDescription>
              All dates and times in the dashboard will be displayed in this timezone
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <label className="text-sm font-medium">Your Timezone</label>
              <Select value={timezone} onValueChange={setTimezone}>
                <SelectTrigger className="w-full sm:w-80">
                  <SelectValue placeholder="Select timezone" />
                </SelectTrigger>
                <SelectContent>
                  {["Americas", "Europe", "Asia", "Oceania", "UTC"].map((group) => (
                    <SelectGroup key={group}>
                      <SelectLabel>{group}</SelectLabel>
                      {TIMEZONE_OPTIONS.filter((tz) => tz.group === group).map((tz) => (
                        <SelectItem key={tz.value} value={tz.value}>
                          {tz.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Current time: {new Date().toLocaleString(undefined, { timeZone: timezone })}
              </p>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Guild Info Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle>Discord Server</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-medium text-muted-foreground">Server ID</dt>
                <dd className="font-mono text-sm">{guild?.id}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">Member Count</dt>
                <dd className="text-sm">{guild?.member_count.toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">Channels</dt>
                <dd className="text-sm">{guild?.channels.length} total</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">Enabled Channels</dt>
                <dd className="text-sm">{guild?.config.enabled_channels.length} channels</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      </motion.div>

      {/* Server Info Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5" />
              Server Info
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-3">
              <div>
                <dt className="text-sm font-medium text-muted-foreground">Version</dt>
                <dd className="text-sm">{health?.version || "—"}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">Build</dt>
                <dd className="font-mono text-sm">{health?.build || "—"}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">Built</dt>
                <dd className="text-sm">
                  {health?.build_date
                    ? formatDistanceToNow(new Date(health.build_date), { addSuffix: true })
                    : "—"}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}

function SettingsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between">
        <div>
          <Skeleton className="mb-2 h-8 w-28" />
          <Skeleton className="h-4 w-48" />
        </div>
      </div>
      <Card className="border-border/50">
        <CardHeader>
          <Skeleton className="mb-2 h-6 w-48" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-6 sm:grid-cols-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
          <div className="space-y-4">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
