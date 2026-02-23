/**
 * Summary Calendar Component (ADR-017)
 *
 * Displays a calendar view of summaries with visual indicators for days
 * that have summaries, their sources, and completeness status.
 */

import { useState } from "react";
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameDay, addMonths, subMonths } from "date-fns";
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, FileText, AlertTriangle, Hash } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useSummaryCalendar } from "@/hooks/useStoredSummaries";

interface CalendarDay {
  date: string;
  count: number;
  sources: string[];
  has_incomplete: boolean;
}

interface SummaryCalendarProps {
  guildId: string;
  onDateSelect: (date: string) => void;
  selectedDate?: string;
}

export function SummaryCalendar({ guildId, onDateSelect, selectedDate }: SummaryCalendarProps) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth() + 1;

  const { data, isLoading } = useSummaryCalendar(guildId, year, month);

  const goToPreviousMonth = () => setCurrentDate(subMonths(currentDate, 1));
  const goToNextMonth = () => setCurrentDate(addMonths(currentDate, 1));
  const goToToday = () => setCurrentDate(new Date());

  // Build a map of dates to calendar data
  const dayDataMap = new Map<string, CalendarDay>();
  if (data?.days) {
    for (const day of data.days) {
      dayDataMap.set(day.date, day);
    }
  }

  // Generate calendar grid
  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const daysInMonth = eachDayOfInterval({ start: monthStart, end: monthEnd });

  // Pad to start on Sunday
  const startPadding = monthStart.getDay();
  const paddedDays: (Date | null)[] = Array(startPadding).fill(null);
  paddedDays.push(...daysInMonth);

  // Pad to complete the last week
  const endPadding = (7 - (paddedDays.length % 7)) % 7;
  paddedDays.push(...Array(endPadding).fill(null));

  // Chunk into weeks
  const weeks: (Date | null)[][] = [];
  for (let i = 0; i < paddedDays.length; i += 7) {
    weeks.push(paddedDays.slice(i, i + 7));
  }

  const weekDays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <CalendarIcon className="h-4 w-4" />
            Summary Calendar
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={goToPreviousMonth}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" className="h-7 px-2 text-sm font-medium" onClick={goToToday}>
              {format(currentDate, "MMMM yyyy")}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={goToNextMonth}
              disabled={addMonths(currentDate, 1) > new Date()}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <CalendarSkeleton />
        ) : (
          <div className="space-y-1">
            {/* Week day headers */}
            <div className="grid grid-cols-7 gap-1">
              {weekDays.map((day) => (
                <div
                  key={day}
                  className="h-8 flex items-center justify-center text-xs font-medium text-muted-foreground"
                >
                  {day}
                </div>
              ))}
            </div>

            {/* Calendar grid */}
            {weeks.map((week, weekIndex) => (
              <div key={weekIndex} className="grid grid-cols-7 gap-1">
                {week.map((day, dayIndex) => {
                  if (!day) {
                    return <div key={dayIndex} className="h-10" />;
                  }

                  const dateStr = format(day, "yyyy-MM-dd");
                  const dayData = dayDataMap.get(dateStr);
                  const isToday = isSameDay(day, new Date());
                  const isSelected = selectedDate === dateStr;
                  const hasSummaries = dayData && dayData.count > 0;
                  const hasIncomplete = dayData?.has_incomplete;

                  return (
                    <TooltipProvider key={dayIndex}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            onClick={() => hasSummaries && onDateSelect(dateStr)}
                            disabled={!hasSummaries}
                            className={cn(
                              "h-10 w-full rounded-md relative flex flex-col items-center justify-center text-sm transition-colors",
                              isToday && "ring-1 ring-primary",
                              isSelected && "bg-primary text-primary-foreground",
                              !isSelected && hasSummaries && "bg-muted hover:bg-muted/80 cursor-pointer",
                              !hasSummaries && "text-muted-foreground cursor-default"
                            )}
                          >
                            <span>{format(day, "d")}</span>
                            {hasSummaries && (
                              <div className="flex gap-0.5 mt-0.5">
                                {dayData.count > 0 && (
                                  <span
                                    className={cn(
                                      "w-1.5 h-1.5 rounded-full",
                                      isSelected ? "bg-primary-foreground" : "bg-primary"
                                    )}
                                  />
                                )}
                                {hasIncomplete && (
                                  <span
                                    className={cn(
                                      "w-1.5 h-1.5 rounded-full",
                                      isSelected ? "bg-yellow-200" : "bg-yellow-500"
                                    )}
                                  />
                                )}
                              </div>
                            )}
                          </button>
                        </TooltipTrigger>
                        {hasSummaries && dayData && (
                          <TooltipContent side="bottom" className="text-xs">
                            <div className="space-y-1">
                              <div className="font-medium">{format(day, "MMMM d, yyyy")}</div>
                              <div className="flex items-center gap-1">
                                <FileText className="h-3 w-3" />
                                {dayData.count} {dayData.count === 1 ? "summary" : "summaries"}
                              </div>
                              {dayData.sources.length > 0 && (
                                <div className="flex flex-wrap gap-1">
                                  {dayData.sources.map((source) => (
                                    <Badge
                                      key={source}
                                      variant="secondary"
                                      className="text-[10px] px-1 py-0"
                                    >
                                      {source}
                                    </Badge>
                                  ))}
                                </div>
                              )}
                              {hasIncomplete && (
                                <div className="flex items-center gap-1 text-yellow-500">
                                  <AlertTriangle className="h-3 w-3" />
                                  <span>Has incomplete data</span>
                                </div>
                              )}
                            </div>
                          </TooltipContent>
                        )}
                      </Tooltip>
                    </TooltipProvider>
                  );
                })}
              </div>
            ))}
          </div>
        )}

        {/* Legend */}
        <div className="mt-4 pt-3 border-t flex flex-wrap gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-primary" />
            <span>Has summaries</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-yellow-500" />
            <span>Incomplete data</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-4 rounded ring-1 ring-primary" />
            <span>Today</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-1">
      <div className="grid grid-cols-7 gap-1">
        {Array(7)
          .fill(0)
          .map((_, i) => (
            <Skeleton key={i} className="h-8" />
          ))}
      </div>
      {Array(5)
        .fill(0)
        .map((_, weekIndex) => (
          <div key={weekIndex} className="grid grid-cols-7 gap-1">
            {Array(7)
              .fill(0)
              .map((_, dayIndex) => (
                <Skeleton key={dayIndex} className="h-10" />
              ))}
          </div>
        ))}
    </div>
  );
}

// Mini calendar for sidebar/compact view
interface MiniCalendarProps {
  guildId: string;
  onDateSelect: (date: string) => void;
}

export function MiniSummaryCalendar({ guildId, onDateSelect }: MiniCalendarProps) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth() + 1;

  const { data } = useSummaryCalendar(guildId, year, month);

  const dayDataMap = new Map<string, CalendarDay>();
  if (data?.days) {
    for (const day of data.days) {
      dayDataMap.set(day.date, day);
    }
  }

  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const daysInMonth = eachDayOfInterval({ start: monthStart, end: monthEnd });

  // Show last 2 weeks with summaries
  const recentDaysWithSummaries = daysInMonth
    .filter((day) => {
      const dateStr = format(day, "yyyy-MM-dd");
      const dayData = dayDataMap.get(dateStr);
      return dayData && dayData.count > 0;
    })
    .slice(-14);

  if (recentDaysWithSummaries.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-muted-foreground">Recent Days</div>
      <div className="flex flex-wrap gap-1">
        {recentDaysWithSummaries.map((day) => {
          const dateStr = format(day, "yyyy-MM-dd");
          const dayData = dayDataMap.get(dateStr);

          return (
            <TooltipProvider key={dateStr}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => onDateSelect(dateStr)}
                    className={cn(
                      "w-8 h-8 rounded text-xs font-medium",
                      "bg-muted hover:bg-muted/80",
                      dayData?.has_incomplete && "ring-1 ring-yellow-500"
                    )}
                  >
                    {format(day, "d")}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="text-xs">
                  {format(day, "MMM d")} - {dayData?.count} summaries
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          );
        })}
      </div>
    </div>
  );
}
