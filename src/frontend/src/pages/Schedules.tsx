import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  useSchedules,
  useUpdateSchedule,
  useDeleteSchedule,
  useRunSchedule,
} from "@/hooks/useSchedules";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { Plus, Calendar, Info, ChevronDown, ChevronUp } from "lucide-react";
import { ScheduleCard } from "@/components/schedules/ScheduleCard";
import { RunHistoryDrawer } from "@/components/schedules/RunHistoryDrawer";
import type { Schedule } from "@/types";

export function Schedules() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: schedules, isLoading } = useSchedules(id || "");
  const updateSchedule = useUpdateSchedule(id || "");
  const deleteSchedule = useDeleteSchedule(id || "");
  const runSchedule = useRunSchedule(id || "");
  const { toast } = useToast();

  const [historySchedule, setHistorySchedule] = useState<Schedule | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [helpExpanded, setHelpExpanded] = useState(false);

  // Navigate to wizard for editing (keeps wizard and edit forms in sync)
  const openEditWizard = (schedule: Schedule) => {
    navigate(`/guilds/${id}/summaries?edit=${schedule.id}`);
  };

  const openHistoryDrawer = (schedule: Schedule) => {
    setHistorySchedule(schedule);
    setHistoryOpen(true);
  };

  const handleToggle = async (scheduleId: string, isActive: boolean) => {
    try {
      await updateSchedule.mutateAsync({
        scheduleId,
        schedule: { is_active: isActive },
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to update schedule.",
        variant: "destructive",
      });
    }
  };

  const handleDelete = async (scheduleId: string) => {
    try {
      await deleteSchedule.mutateAsync(scheduleId);
      toast({
        title: "Schedule deleted",
        description: "The schedule has been removed.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to delete schedule.",
        variant: "destructive",
      });
    }
  };

  const handleRunNow = async (scheduleId: string) => {
    try {
      await runSchedule.mutateAsync(scheduleId);
      toast({
        title: "Schedule triggered",
        description: "The schedule is running now.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to run schedule.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold">Schedules</h1>
          <p className="text-muted-foreground">
            Automate summary generation on a schedule
          </p>
        </div>

        {/* Link to Summaries page wizard */}
        <Button asChild>
          <Link to={`/guilds/${id}/summaries?create=schedule`}>
            <Plus className="mr-2 h-4 w-4" />
            Create Schedule
          </Link>
        </Button>
      </motion.div>

      {/* Help Note */}
      <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20">
        <CardContent className="p-4">
          <button
            onClick={() => setHelpExpanded(!helpExpanded)}
            className="flex w-full items-center justify-between text-left"
          >
            <div className="flex items-center gap-2 text-sm font-medium text-blue-700 dark:text-blue-300">
              <Info className="h-4 w-4" />
              Normal vs Rolling Schedules
            </div>
            {helpExpanded ? (
              <ChevronUp className="h-4 w-4 text-blue-600 dark:text-blue-400" />
            ) : (
              <ChevronDown className="h-4 w-4 text-blue-600 dark:text-blue-400" />
            )}
          </button>
          {helpExpanded && (
            <div className="mt-3 space-y-2 text-sm text-blue-800 dark:text-blue-200">
              <p>
                <strong>Normal Schedule:</strong> Each run creates a new summary document.
                A daily schedule produces 7 separate summaries per week.
              </p>
              <p>
                <strong>Rolling Schedule:</strong> Accumulates content into one summary per period.
                A daily schedule with weekly rolling produces 1 summary that builds up all week,
                then finalizes and starts fresh.
              </p>
              <p className="text-xs text-blue-600 dark:text-blue-400">
                Enable rolling periods in the "When" step when creating or editing a schedule.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {isLoading ? (
        <SchedulesSkeleton />
      ) : schedules?.length === 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center justify-center py-20"
        >
          <Calendar className="mb-4 h-16 w-16 text-muted-foreground/30" />
          <h2 className="mb-2 text-xl font-semibold">No schedules yet</h2>
          <p className="mb-6 text-center text-muted-foreground">
            Create your first schedule to automate summaries
          </p>
          <Button asChild>
            <Link to={`/guilds/${id}/summaries?create=schedule`}>
              <Plus className="mr-2 h-4 w-4" />
              Create Schedule
            </Link>
          </Button>
        </motion.div>
      ) : (
        <div className="space-y-4">
          {schedules?.map((schedule, index) => (
            <ScheduleCard
              key={schedule.id}
              schedule={schedule}
              index={index}
              onToggle={handleToggle}
              onEdit={openEditWizard}
              onDelete={handleDelete}
              onRunNow={handleRunNow}
              onViewHistory={openHistoryDrawer}
              isDeleting={deleteSchedule.isPending}
              isRunning={runSchedule.isPending}
            />
          ))}
        </div>
      )}

      {/* Run History Drawer */}
      <RunHistoryDrawer
        schedule={historySchedule}
        open={historyOpen}
        onOpenChange={setHistoryOpen}
      />
    </div>
  );
}

function SchedulesSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <Card key={i} className="border-border/50">
          <CardContent className="p-5">
            <div className="flex justify-between">
              <div className="space-y-3">
                <div className="flex gap-2">
                  <Skeleton className="h-5 w-40" />
                  <Skeleton className="h-5 w-16" />
                </div>
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-4 w-32" />
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-6 w-10" />
                <Skeleton className="h-8 w-8" />
                <Skeleton className="h-8 w-8" />
                <Skeleton className="h-8 w-8" />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
