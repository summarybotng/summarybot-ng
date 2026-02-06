import { formatDistanceToNow } from "date-fns";
import { motion } from "framer-motion";
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
import { Play, Trash2, Calendar, Clock, Pencil } from "lucide-react";
import type { Schedule } from "@/types";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

interface ScheduleCardProps {
  schedule: Schedule;
  index: number;
  onToggle: (id: string, active: boolean) => void;
  onEdit: (schedule: Schedule) => void;
  onDelete: (id: string) => void;
  onRunNow: (id: string) => void;
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
  isDeleting,
  isRunning,
}: ScheduleCardProps) {
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
              </div>

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

              <div className="flex gap-4 text-sm text-muted-foreground">
                <span>Runs: {schedule.run_count}</span>
                <span>Failures: {schedule.failure_count}</span>
                {schedule.next_run && (
                  <span>
                    Next: {new Date(schedule.next_run).toLocaleString()} (
                    {formatDistanceToNow(
                      new Date(Math.max(new Date(schedule.next_run).getTime(), Date.now())),
                      { addSuffix: true }
                    )}
                    )
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Switch
                checked={schedule.is_active}
                onCheckedChange={(checked) => onToggle(schedule.id, checked)}
              />

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
