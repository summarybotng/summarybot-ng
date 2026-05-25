/**
 * Unified Summary Wizard (ADR-089)
 *
 * Single entry point for all summary creation:
 * - Generate now (immediate)
 * - Schedule recurring
 * - Generate past (retrospective)
 */

import { useState, useCallback, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Loader2, ArrowLeft, ArrowRight, Sparkles, Calendar, Info } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useGuild } from "@/hooks/useGuilds";
import { WizardProgress } from "./shared/WizardProgress";
import { WhatStep } from "./steps/WhatStep";
import { WhenStep } from "./steps/WhenStep";
import { WhereStep } from "./steps/WhereStep";
import type { WizardState, WizardStep, WhenType, Platform, SplitMode } from "./types";
import { initialWizardState, scheduleToWizardState } from "./types";
import type { Schedule } from "@/types";

// LocalStorage key for persisting wizard selections
const getStorageKey = (guildId: string) => `wizard_selection_${guildId}`;

interface PersistedSelection {
  platform: Platform;
  scope: "channel" | "category" | "guild";
  channelIds: string[];
  categoryId: string;
  splitMode: SplitMode;  // ADR-094
}

interface SummaryWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  guildId: string;
  initialWhenType?: WhenType;
  /** Schedule to edit (enables edit mode) */
  editSchedule?: Schedule | null;
  onGenerateNow?: (state: WizardState) => Promise<void>;
  onCreateSchedule?: (state: WizardState) => Promise<void>;
  /** Called when updating an existing schedule */
  onUpdateSchedule?: (scheduleId: string, state: WizardState) => Promise<void>;
  onGeneratePast?: (state: WizardState) => Promise<void>;
}

export function SummaryWizard({
  open,
  onOpenChange,
  guildId,
  initialWhenType = "now",
  editSchedule,
  onGenerateNow,
  onCreateSchedule,
  onUpdateSchedule,
  onGeneratePast,
}: SummaryWizardProps) {
  const isEditMode = !!editSchedule;

  const [state, setState] = useState<WizardState>(() => ({
    ...initialWizardState,
    whenType: initialWhenType,
  }));
  const [step, setStep] = useState<WizardStep>("what");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hasRestoredSelection, setHasRestoredSelection] = useState(false);
  const [hasLoadedEditData, setHasLoadedEditData] = useState(false);
  const { toast } = useToast();
  const { data: guild } = useGuild(guildId);

  // Load edit schedule data when opening in edit mode
  useEffect(() => {
    if (open && editSchedule && !hasLoadedEditData) {
      const editState = scheduleToWizardState(editSchedule);
      setState(editState);
      setHasLoadedEditData(true);
    }
    // Reset when dialog closes
    if (!open) {
      setHasLoadedEditData(false);
    }
  }, [open, editSchedule, hasLoadedEditData]);

  // Restore selection from localStorage when wizard opens (skip in edit mode)
  useEffect(() => {
    if (open && guildId && !hasRestoredSelection && !isEditMode) {
      try {
        const saved = localStorage.getItem(getStorageKey(guildId));
        if (saved) {
          const selection: PersistedSelection = JSON.parse(saved);
          setState((prev) => ({
            ...prev,
            platform: selection.platform || prev.platform,
            scope: selection.scope || prev.scope,
            channelIds: selection.channelIds || [],
            categoryId: selection.categoryId || "",
            splitMode: selection.splitMode || prev.splitMode,  // ADR-094
          }));
        }
      } catch (e) {
        console.warn("Failed to restore wizard selection:", e);
      }
      setHasRestoredSelection(true);
    }
    // Reset restoration flag when dialog closes
    if (!open) {
      setHasRestoredSelection(false);
    }
  }, [open, guildId, hasRestoredSelection, isEditMode]);

  // Save selection to localStorage when it changes
  useEffect(() => {
    if (guildId && hasRestoredSelection) {
      const selection: PersistedSelection = {
        platform: state.platform,
        scope: state.scope,
        channelIds: state.channelIds,
        categoryId: state.categoryId,
        splitMode: state.splitMode,  // ADR-094
      };
      try {
        localStorage.setItem(getStorageKey(guildId), JSON.stringify(selection));
      } catch (e) {
        console.warn("Failed to save wizard selection:", e);
      }
    }
  }, [guildId, state.platform, state.scope, state.channelIds, state.categoryId, state.splitMode, hasRestoredSelection]);

  const handleChange = useCallback((updates: Partial<WizardState>) => {
    setState((prev) => ({ ...prev, ...updates }));
  }, []);

  const handleClose = () => {
    onOpenChange(false);
    // Reset step and non-selection state after animation
    // Keep platform, scope, channelIds, categoryId, splitMode to persist selection
    setTimeout(() => {
      setState((prev) => ({
        ...initialWizardState,
        whenType: initialWhenType,
        // Preserve selection state
        platform: prev.platform,
        scope: prev.scope,
        channelIds: prev.channelIds,
        categoryId: prev.categoryId,
        splitMode: prev.splitMode,  // ADR-094
      }));
      setStep("what");
    }, 200);
  };

  const canProceedFromWhat = () => {
    if (state.scope === "channel" && state.channelIds.length === 0) {
      return false;
    }
    if (state.scope === "category" && !state.categoryId) {
      return false;
    }
    return true;
  };

  const canProceedFromWhen = () => {
    if (state.whenType === "now") {
      if (state.timeRange === "custom" && !state.customHours) {
        return false;
      }
    }
    if (state.whenType === "recurring") {
      // Schedule name is optional - will use auto-generated if empty
      if (state.frequency === "weekly" && state.scheduleDays.length === 0) {
        return false;
      }
    }
    if (state.whenType === "past") {
      if (!state.dateFrom || !state.dateTo) {
        return false;
      }
      // Weekly past requires at least one day selected
      if (state.pastGranularity === "weekly" && state.pastScheduleDays.length === 0) {
        return false;
      }
    }
    return true;
  };

  const handleNext = () => {
    if (step === "what") {
      setStep("when");
    } else if (step === "when") {
      setStep("where");
    } else if (step === "where") {
      handleSubmit();
    }
  };

  const handleBack = () => {
    if (step === "when") {
      setStep("what");
    } else if (step === "where") {
      setStep("when");
    }
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      if (isEditMode && editSchedule && onUpdateSchedule) {
        // Edit mode: update existing schedule
        await onUpdateSchedule(editSchedule.id, state);
      } else if (state.whenType === "now" && onGenerateNow) {
        await onGenerateNow(state);
      } else if (state.whenType === "recurring" && onCreateSchedule) {
        await onCreateSchedule(state);
      } else if (state.whenType === "past" && onGeneratePast) {
        await onGeneratePast(state);
      }
      handleClose();
    } catch (error: any) {
      console.error("Wizard submit error:", error);
      // Extract error message from API response
      const errorMessage = error?.response?.data?.detail
        || error?.detail
        || error?.message
        || "An unexpected error occurred";
      toast({
        title: isEditMode ? "Update failed" : "Generation failed",
        description: errorMessage,
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const getSubmitLabel = () => {
    if (isEditMode) return "Save Changes";
    if (state.whenType === "now") return "Generate Now";
    if (state.whenType === "recurring") return "Create Schedule";
    if (state.whenType === "past") return "Generate";
    return "Submit";
  };

  const getSubmitIcon = () => {
    if (state.whenType === "now") return <Sparkles className="h-4 w-4 mr-2" />;
    if (state.whenType === "recurring") return <Calendar className="h-4 w-4 mr-2" />;
    if (state.whenType === "past") return <Sparkles className="h-4 w-4 mr-2" />;
    return null;
  };

  const isLastStep = step === "where";

  const canProceed =
    (step === "what" && canProceedFromWhat()) ||
    (step === "when" && canProceedFromWhen()) ||
    step === "where";

  // Free step navigation
  const handleStepClick = useCallback((targetStep: WizardStep) => {
    setStep(targetStep);
  }, []);

  // Generate English summary of what this schedule will do
  const summaryText = useMemo(() => {
    const parts: string[] = [];

    // What: channels/scope
    const channelNames = state.channelIds
      .map((id) => {
        const channel = guild?.channels?.find((c) => c.id === id);
        return channel ? `#${channel.name}` : null;
      })
      .filter(Boolean);

    const categoryName = state.categoryId
      ? guild?.categories?.find((c) => c.id === state.categoryId)?.name
      : null;

    let sourceText = "";
    let channelsForTitle = "";
    if (state.scope === "guild") {
      sourceText = "all channels in this server";
      channelsForTitle = "Server";
    } else if (state.scope === "category" && categoryName) {
      sourceText = `all channels in the "${categoryName}" category`;
      channelsForTitle = categoryName;
    } else if (channelNames.length > 0) {
      sourceText = channelNames.length === 1
        ? channelNames[0]!
        : `${channelNames.slice(0, -1).join(", ")} and ${channelNames[channelNames.length - 1]}`;
      channelsForTitle = channelNames.length === 1
        ? channelNames[0]!.replace("#", "")
        : `${channelNames.length} channels`;
    } else {
      sourceText = "selected channels";
      channelsForTitle = "Channels";
    }

    // Platform
    const platformLabel = state.platform === "discord" ? "Discord" : state.platform === "slack" ? "Slack" : "WhatsApp";

    // Date range calculation
    let dateRangeText = "";
    const now = new Date();
    if (state.whenType === "now") {
      const hours = state.timeRange === "custom" ? (state.customHours || 24) : parseInt(state.timeRange);
      const startDate = new Date(now.getTime() - hours * 60 * 60 * 1000);
      dateRangeText = `${startDate.toLocaleDateString()} ${startDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} — ${now.toLocaleDateString()} ${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } else if (state.whenType === "recurring") {
      const hours = state.lookbackHours || 24;
      dateRangeText = `Last ${hours} hours of messages each run`;
    } else if (state.whenType === "past") {
      const fromStr = state.dateFrom ? state.dateFrom.toLocaleDateString() : "?";
      const toStr = state.dateTo ? state.dateTo.toLocaleDateString() : "?";
      dateRangeText = `${fromStr} — ${toStr}`;
    }

    // When: timing
    let whenText = "";
    if (state.whenType === "now") {
      const hours = state.timeRange === "custom" ? state.customHours : parseInt(state.timeRange);
      whenText = `from the last ${hours} hours`;
    } else if (state.whenType === "recurring") {
      const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
      const freqLabel = state.frequency === "fifteen-minutes" ? "every 15 minutes"
        : state.frequency === "hourly" ? "every hour"
        : state.frequency === "every-4-hours" ? "every 4 hours"
        : state.frequency === "daily" ? "daily"
        : state.frequency === "weekly" ? `weekly on ${state.scheduleDays.map(d => DAYS[d]).join(", ")}`
        : state.frequency === "monthly" ? "monthly"
        : state.frequency;
      whenText = `${freqLabel} at ${state.scheduleTime} (${state.timezone})`;
    } else if (state.whenType === "past") {
      const fromStr = state.dateFrom ? state.dateFrom.toLocaleDateString() : "?";
      const toStr = state.dateTo ? state.dateTo.toLocaleDateString() : "?";
      whenText = `for the period ${fromStr} to ${toStr}`;
    }

    // Where: destinations
    const destinations: string[] = [];
    if (state.destinations.dashboard) destinations.push("the dashboard");
    if (state.destinations.discordChannel && state.destinations.discordChannelId) {
      const destChannel = guild?.channels?.find((c) => c.id === state.destinations.discordChannelId);
      destinations.push(destChannel ? `#${destChannel.name}` : "a Discord channel");
    }
    if (state.destinations.discordDm) destinations.push("Discord DM");
    if (state.destinations.webhook) destinations.push("a webhook");
    if (state.destinations.email) destinations.push("email");
    if (state.destinations.confluence) destinations.push("Confluence");

    const destText = destinations.length > 0
      ? destinations.length === 1
        ? destinations[0]
        : `${destinations.slice(0, -1).join(", ")} and ${destinations[destinations.length - 1]}`
      : "the dashboard";

    // Generate title preview
    const titleTemplate = state.pageTitleTemplate || "{channels} Summary - {date}";
    const titlePreview = titleTemplate
      .replace("{channels}", channelsForTitle)
      .replace("{date}", now.toLocaleDateString());

    // Split mode description
    const splitModeText = state.splitMode === "consolidated" ? "combined into one"
      : state.splitMode === "by-category" ? "split by category"
      : "split per channel";

    // Perspective description
    const perspectiveText = state.perspective && state.perspective !== "general"
      ? ` from a ${state.perspective} perspective`
      : "";

    // Build the summary
    if (state.whenType === "now") {
      parts.push(`Generate a ${state.summaryLength} summary${perspectiveText} of ${platformLabel} messages in ${sourceText} ${whenText}.`);
      parts.push(`Date range: ${dateRangeText}.`);
      if ((state.scope === "category" || state.scope === "guild") && state.platform === "discord") {
        parts.push(`Summaries ${splitModeText}.`);
      }
      if (state.minMessages > 0) {
        parts.push(`Requires at least ${state.minMessages} messages.`);
      }
      parts.push(`Deliver to ${destText}.`);
    } else if (state.whenType === "recurring") {
      const actionVerb = isEditMode ? "will continue to summarize" : "will summarize";
      parts.push(`This schedule ${actionVerb} ${platformLabel} messages in ${sourceText} ${whenText}.`);
      parts.push(`${dateRangeText}.`);
      parts.push(`${state.summaryLength.charAt(0).toUpperCase() + state.summaryLength.slice(1)} summaries${perspectiveText}.`);
      if ((state.scope === "category" || state.scope === "guild") && state.platform === "discord") {
        parts.push(`Summaries ${splitModeText}.`);
      }
      if (state.rollingPeriod !== "none") {
        const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
        const endDayName = DAYS[state.rollingEndDay] || "Saturday";
        const periodLabel = state.rollingPeriod === "weekly" ? "week"
          : state.rollingPeriod === "biweekly" ? "two weeks"
          : "month";
        const strategyExplain = state.accumulationStrategy === "append"
          ? "each daily summary is added to build a complete picture"
          : state.accumulationStrategy === "resummarize"
          ? "all messages are re-summarized together at the end"
          : "daily summaries are combined and refined at the end";
        parts.push(`Rolling ${state.rollingPeriod} period: summaries accumulate over ${periodLabel}, finalizing every ${endDayName}. Strategy: ${strategyExplain}.`);
      }
      if (state.enableContinuity) {
        parts.push(`Continuity enabled (references previous summaries).`);
      }
      if (state.minMessages > 0) {
        parts.push(`Requires at least ${state.minMessages} messages.`);
      }
      parts.push(`Deliver to ${destText}.`);
    } else if (state.whenType === "past") {
      const granularityText = state.pastGranularity === "single" ? "a single summary"
        : state.pastGranularity === "daily" ? "daily summaries"
        : "weekly summaries";
      parts.push(`Generate ${granularityText}${perspectiveText} of ${platformLabel} messages in ${sourceText} ${whenText}.`);
      parts.push(`Date range: ${dateRangeText}.`);
      parts.push(`${state.summaryLength.charAt(0).toUpperCase() + state.summaryLength.slice(1)} detail level.`);
      if (state.perChannel && state.channelIds.length > 1) {
        parts.push(`One summary per channel.`);
      }
      if (state.forceRegenerate) {
        parts.push(`Will overwrite existing summaries.`);
      }
      if (state.minMessages > 0) {
        parts.push(`Requires at least ${state.minMessages} messages.`);
      }
      parts.push(`Deliver to ${destText}.`);
    }

    return { description: parts.join(" "), title: titlePreview };
  }, [state, guild, isEditMode]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditMode ? "Edit Schedule" : "Create Summary"}</DialogTitle>
        </DialogHeader>

        {/* Summary Preview - always visible at top */}
        <div className="p-4 rounded-lg bg-primary/5 border border-primary/20">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="h-4 w-4 text-primary shrink-0" />
            <span className="font-medium text-sm">{summaryText.title}</span>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {summaryText.description}
          </p>
        </div>

        <WizardProgress currentStep={step} whenType={state.whenType} onStepClick={handleStepClick} />

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.2 }}
          >
            {step === "what" && (
              <WhatStep state={state} onChange={handleChange} guildId={guildId} />
            )}
            {step === "when" && (
              <WhenStep state={state} onChange={handleChange} guildId={guildId} />
            )}
            {step === "where" && (
              <WhereStep state={state} onChange={handleChange} guildId={guildId} />
            )}
          </motion.div>
        </AnimatePresence>

        {/* Navigation */}
        <div className="flex justify-between pt-4 border-t">
          <Button
            type="button"
            variant="ghost"
            onClick={step === "what" ? handleClose : handleBack}
          >
            {step === "what" ? (
              "Cancel"
            ) : (
              <>
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back
              </>
            )}
          </Button>

          <Button
            type="button"
            onClick={handleNext}
            disabled={!canProceed || isSubmitting}
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Processing...
              </>
            ) : isLastStep ? (
              <>
                {getSubmitIcon()}
                {getSubmitLabel()}
              </>
            ) : (
              <>
                Next
                <ArrowRight className="h-4 w-4 ml-2" />
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
