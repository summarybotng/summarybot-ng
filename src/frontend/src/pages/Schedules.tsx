import { useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  useSchedules,
  useCreateSchedule,
  useUpdateSchedule,
  useDeleteSchedule,
  useRunSchedule,
} from "@/hooks/useSchedules";
import { useGuild } from "@/hooks/useGuilds";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { Plus, Calendar, Loader2, Pencil } from "lucide-react";
import { ScheduleCard } from "@/components/schedules/ScheduleCard";
import { RunHistoryDrawer } from "@/components/schedules/RunHistoryDrawer";
import {
  ScheduleForm,
  getInitialFormData,
  scheduleToFormData,
  formDataToDestinations,
  type ScheduleFormData,
} from "@/components/schedules/ScheduleForm";
import type { Schedule } from "@/types";

export function Schedules() {
  const { id } = useParams<{ id: string }>();
  const { data: schedules, isLoading } = useSchedules(id || "");
  const { data: guild } = useGuild(id || "");
  const createSchedule = useCreateSchedule(id || "");
  const updateSchedule = useUpdateSchedule(id || "");
  const deleteSchedule = useDeleteSchedule(id || "");
  const runSchedule = useRunSchedule(id || "");
  const { toast } = useToast();

  const [createOpen, setCreateOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null);
  const [historySchedule, setHistorySchedule] = useState<Schedule | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [formData, setFormData] = useState<ScheduleFormData>(() => getInitialFormData());

  const resetForm = () => {
    setFormData(getInitialFormData());
  };

  const openEditDialog = (schedule: Schedule) => {
    setFormData(scheduleToFormData(schedule));
    setEditingSchedule(schedule);
  };

  const openHistoryDrawer = (schedule: Schedule) => {
    setHistorySchedule(schedule);
    setHistoryOpen(true);
  };

  const handleCreate = async () => {
    try {
      // ADR-011: Determine channel_ids based on scope
      let channelIds: string[] = [];
      if (formData.scope === "channel") {
        channelIds = formData.channel_ids.length > 0
          ? formData.channel_ids
          : guild?.config.enabled_channels || [];
      }
      // For category and guild scopes, channels are resolved server-side

      await createSchedule.mutateAsync({
        name: formData.name,
        scope: formData.scope,
        channel_ids: channelIds,
        category_id: formData.scope === "category" ? formData.category_id : undefined,
        schedule_type: formData.schedule_type,
        schedule_time: formData.schedule_time,
        schedule_days: formData.schedule_type === "weekly" ? formData.schedule_days : undefined,
        timezone: formData.timezone,
        destinations: formDataToDestinations(formData),
        summary_options: {
          summary_length: formData.summary_length,
          perspective: formData.perspective,
          include_action_items: true,
          include_technical_terms: true,
        },
      });
      setCreateOpen(false);
      resetForm();
      toast({
        title: "Schedule created",
        description: "Your new schedule has been created.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to create schedule.",
        variant: "destructive",
      });
    }
  };

  const handleEdit = async () => {
    if (!editingSchedule) return;

    try {
      // ADR-011: Determine channel_ids based on scope
      let channelIds: string[] | undefined = undefined;
      if (formData.scope === "channel") {
        channelIds = formData.channel_ids.length > 0
          ? formData.channel_ids
          : guild?.config.enabled_channels || [];
      }

      await updateSchedule.mutateAsync({
        scheduleId: editingSchedule.id,
        schedule: {
          name: formData.name,
          scope: formData.scope,
          channel_ids: channelIds,
          category_id: formData.scope === "category" ? formData.category_id : undefined,
          schedule_type: formData.schedule_type,
          schedule_time: formData.schedule_time,
          schedule_days: formData.schedule_type === "weekly" ? formData.schedule_days : undefined,
          timezone: formData.timezone,
          destinations: formDataToDestinations(formData),
          summary_options: {
            summary_length: formData.summary_length,
            perspective: formData.perspective,
            include_action_items: true,
            include_technical_terms: true,
          },
        },
      });
      setEditingSchedule(null);
      resetForm();
      toast({
        title: "Schedule updated",
        description: "Your schedule has been updated.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to update schedule.",
        variant: "destructive",
      });
    }
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

        {/* Create Dialog */}
        <Dialog open={createOpen} onOpenChange={(open) => {
          setCreateOpen(open);
          if (!open) resetForm();
        }}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Create Schedule
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Schedule</DialogTitle>
              <DialogDescription>
                Set up an automated summary schedule
              </DialogDescription>
            </DialogHeader>
            <ScheduleForm
              formData={formData}
              onChange={setFormData}
              channels={guild?.channels || []}
              categories={guild?.categories || []}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!formData.name || createSchedule.isPending}
              >
                {createSchedule.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="mr-2 h-4 w-4" />
                )}
                Create
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </motion.div>

      {/* Edit Dialog */}
      <Dialog
        open={!!editingSchedule}
        onOpenChange={(open) => {
          if (!open) {
            setEditingSchedule(null);
            resetForm();
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Schedule</DialogTitle>
            <DialogDescription>
              Modify your automated summary schedule
            </DialogDescription>
          </DialogHeader>
          <ScheduleForm
            formData={formData}
            onChange={setFormData}
            channels={guild?.channels || []}
            categories={guild?.categories || []}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingSchedule(null)}>
              Cancel
            </Button>
            <Button
              onClick={handleEdit}
              disabled={!formData.name || updateSchedule.isPending}
            >
              {updateSchedule.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Pencil className="mr-2 h-4 w-4" />
              )}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Create Schedule
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
              onEdit={openEditDialog}
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
