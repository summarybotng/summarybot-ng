import { motion } from "framer-motion";
import { useTimezone, formatRelativeTime } from "@/contexts/TimezoneContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Play, Trash2, Calendar, Clock, Pencil, History, MessageSquare, Copy, Check, RefreshCw, LayoutDashboard, Bell, Mail, Globe, FileText, FileStack, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Schedule } from "@/types";
import { useRollingSummaries } from "@/hooks/useSchedules";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Destination type to display info
const DESTINATION_INFO: Record<string, { label: string; icon: React.ReactNode; className: string }> = {
  dashboard: {
    label: "Dashboard",
    icon: <LayoutDashboard className="h-3 w-3" />,
    className: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  },
  discord_channel: {
    label: "Discord",
    icon: <MessageSquare className="h-3 w-3" />,
    className: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300",
  },
  discord_dm: {
    label: "DM",
    icon: <Bell className="h-3 w-3" />,
    className: "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
  },
  webhook: {
    label: "Webhook",
    icon: <Globe className="h-3 w-3" />,
    className: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  },
  email: {
    label: "Email",
    icon: <Mail className="h-3 w-3" />,
    className: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
  },
  confluence: {
    label: "Confluence",
    icon: <FileText className="h-3 w-3" />,
    className: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300",
  },
};

// ADR-051: Platform badge helper
function getPlatformBadge(platform?: string) {
  const p = platform || "discord";
  if (p === "slack") {
    return {
      label: "Slack",
      icon: <MessageSquare className="h-3 w-3 mr-1" />,
      className: "bg-[#4A154B] text-white hover:bg-[#4A154B]/90",
    };
  }
  return {
    label: "Discord",
    icon: <span className="mr-1">🎮</span>,
    className: "bg-[#5865F2] text-white hover:bg-[#5865F2]/90",
  };
}

interface ScheduleCardProps {
  schedule: Schedule;
  index: number;
  onToggle: (id: string, active: boolean) => void;
  onEdit: (schedule: Schedule) => void;
  onDelete: (id: string) => void;
  onRunNow: (id: string) => void;
  onViewHistory: (schedule: Schedule) => void;
  isDeleting: boolean;
  isRunning: boolean;
}

export function ScheduleCard({
  schedule,
  index,
  onToggle,
  onEdit,
  onDelete,
  onRunNow,
  onViewHistory,
  isDeleting,
  isRunning,
}: ScheduleCardProps) {
  const [copied, setCopied] = useState(false);
  const { guildId } = useParams<{ guildId: string }>();
  const { formatDateTime } = useTimezone();

  // ADR-104: Fetch rolling summaries for rolling schedules
  const { data: rollingSummaries } = useRollingSummaries(
    guildId || "",
    schedule.id,
    !!schedule.rolling_period
  );

  const copyId = () => {
    navigator.clipboard.writeText(schedule.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card className="border-border/50">
        <CardContent className="p-5">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="mb-2 flex items-center gap-3">
                <h3 className="font-semibold">{schedule.name}</h3>
                <Badge variant={schedule.is_active ? "default" : "secondary"}>
                  {schedule.is_active ? "Active" : "Inactive"}
                </Badge>
                {/* ADR-051: Platform badge */}
                <Badge className={getPlatformBadge(schedule.platform).className}>
                  {getPlatformBadge(schedule.platform).icon}
                  {getPlatformBadge(schedule.platform).label}
                </Badge>
                {/* ADR-101: Rolling period badge */}
                {schedule.rolling_period && (
                  <Badge variant="outline" className="gap-1 text-orange-600 border-orange-300 bg-orange-50 dark:bg-orange-950/30 dark:text-orange-400 dark:border-orange-800">
                    <RefreshCw className="h-3 w-3" />
                    {schedule.rolling_period === "weekly" ? "Weekly Rolling" :
                     schedule.rolling_period === "biweekly" ? "Biweekly Rolling" :
                     schedule.rolling_period === "monthly" ? "Monthly Rolling" : "Rolling"}
                  </Badge>
                )}
              </div>

              {/* Destination chips */}
              {schedule.destinations && schedule.destinations.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {schedule.destinations
                    .filter(d => d.enabled !== false)
                    .map((dest, idx) => {
                      const info = DESTINATION_INFO[dest.type];
                      if (!info) return null;
                      return (
                        <Badge
                          key={`${dest.type}-${idx}`}
                          variant="secondary"
                          className={`gap-1 text-xs font-normal ${info.className}`}
                        >
                          {info.icon}
                          {info.label}
                        </Badge>
                      );
                    })}
                </div>
              )}

              <div className="mb-3 flex flex-wrap gap-3 text-sm text-muted-foreground">
                <div className="flex items-center gap-1.5">
                  <Calendar className="h-4 w-4" />
                  <span className="capitalize">{schedule.schedule_type}</span>
                  {schedule.schedule_type === "weekly" && schedule.schedule_days && (
                    <span>
                      ({schedule.schedule_days.map((d) => DAYS[d]).join(", ")})
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  <Clock className="h-4 w-4" />
                  <span>
                    {schedule.schedule_time} ({schedule.timezone})
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                <span>Runs: {schedule.run_count}</span>
                <span>Failures: {schedule.failure_count}</span>
                {/* Issue #19: Show last run time */}
                {schedule.last_run && (
                  <span>
                    Last: {formatRelativeTime(schedule.last_run)}
                  </span>
                )}
                {schedule.next_run && (
                  <span>
                    Next: {formatRelativeTime(schedule.next_run)}
                  </span>
                )}
                <button
                  onClick={copyId}
                  className="flex items-center gap-1 text-xs font-mono opacity-60 hover:opacity-100 transition-opacity"
                  title="Click to copy Schedule ID"
                >
                  ID: {schedule.id}
                  {copied ? (
                    <Check className="h-3 w-3 text-green-500" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  )}
                </button>
              </div>

              {/* ADR-104: Rolling summaries display */}
              {schedule.rolling_period && rollingSummaries && (
                <div className="mt-4 pt-4 border-t border-border/50">
                  {/* Current rolling summary */}
                  {rollingSummaries.current && (
                    <div className="mb-3">
                      <div className="flex items-center gap-2 mb-2">
                        <FileStack className="h-4 w-4 text-orange-500" />
                        <span className="text-sm font-medium">Current Period</span>
                        <Badge variant="outline" className="text-xs bg-orange-50 text-orange-600 border-orange-200 dark:bg-orange-950/30 dark:text-orange-400 dark:border-orange-800">
                          Rolling
                        </Badge>
                      </div>
                      <Link
                        to={`/guilds/${guildId}/summaries?view=${rollingSummaries.current.summary_id}`}
                        className="block p-3 rounded-md bg-muted/50 hover:bg-muted transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-sm">{rollingSummaries.current.title}</span>
                          <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        </div>
                        <div className="flex flex-wrap gap-3 mt-1 text-xs text-muted-foreground">
                          <span>Day {rollingSummaries.current.accumulation_count} of {rollingSummaries.current.total_days_in_period}</span>
                          <span>Rollover: {formatDateTime(rollingSummaries.current.rollover_date)}</span>
                          <span>{rollingSummaries.current.message_count} messages</span>
                        </div>
                      </Link>
                    </div>
                  )}

                  {/* Previous finalized summaries */}
                  {rollingSummaries.previous.length > 0 && (
                    <div>
                      <div className="text-xs text-muted-foreground mb-2">Previous Periods</div>
                      <div className="space-y-1">
                        {rollingSummaries.previous.map((summary) => (
                          <Link
                            key={summary.summary_id}
                            to={`/guilds/${guildId}/summaries?view=${summary.summary_id}`}
                            className="flex items-center justify-between p-2 rounded-md hover:bg-muted/50 transition-colors text-sm"
                          >
                            <span className="text-muted-foreground">{summary.title}</span>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-muted-foreground">{summary.message_count} msgs</span>
                              <ChevronRight className="h-3 w-3 text-muted-foreground" />
                            </div>
                          </Link>
                        ))}
                      </div>
                      {rollingSummaries.total_finalized_count > rollingSummaries.previous.length && (
                        <Link
                          to={`/guilds/${guildId}/summaries?schedule=${schedule.id}`}
                          className="block mt-2 text-xs text-primary hover:underline"
                        >
                          View all {rollingSummaries.total_finalized_count} summaries →
                        </Link>
                      )}
                    </div>
                  )}

                  {/* Empty state */}
                  {!rollingSummaries.current && rollingSummaries.previous.length === 0 && (
                    <div className="text-sm text-muted-foreground">
                      No summaries yet. Run the schedule to generate the first rolling summary.
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              <Switch
                checked={schedule.is_active}
                onCheckedChange={(checked) => onToggle(schedule.id, checked)}
              />

              <Button
                variant="ghost"
                size="icon"
                onClick={() => onViewHistory(schedule)}
                title="View run history"
              >
                <History className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="icon"
                onClick={() => onEdit(schedule)}
                title="Edit schedule"
              >
                <Pencil className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="icon"
                onClick={() => onRunNow(schedule.id)}
                disabled={isRunning}
                title="Run now"
              >
                <Play className="h-4 w-4" />
              </Button>

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="icon" title="Delete schedule">
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete Schedule</AlertDialogTitle>
                    <AlertDialogDescription>
                      Are you sure you want to delete "{schedule.name}"? This action
                      cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => onDelete(schedule.id)}
                      disabled={isDeleting}
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
