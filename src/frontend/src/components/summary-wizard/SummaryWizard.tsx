/**
 * Unified Summary Wizard (ADR-089)
 *
 * Single entry point for all summary creation:
 * - Generate now (immediate)
 * - Schedule recurring
 * - Generate past (retrospective)
 */

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Loader2, ArrowLeft, ArrowRight, Sparkles, Calendar } from "lucide-react";
import { WizardProgress } from "./shared/WizardProgress";
import { WhatStep } from "./steps/WhatStep";
import { WhenStep } from "./steps/WhenStep";
import { DeliveryStep } from "./steps/DeliveryStep";
import type { WizardState, WizardStep, WhenType } from "./types";
import { initialWizardState } from "./types";

interface SummaryWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  guildId: string;
  initialWhenType?: WhenType;
  onGenerateNow?: (state: WizardState) => Promise<void>;
  onCreateSchedule?: (state: WizardState) => Promise<void>;
  onGeneratePast?: (state: WizardState) => Promise<void>;
}

export function SummaryWizard({
  open,
  onOpenChange,
  guildId,
  initialWhenType = "now",
  onGenerateNow,
  onCreateSchedule,
  onGeneratePast,
}: SummaryWizardProps) {
  const [state, setState] = useState<WizardState>(() => ({
    ...initialWizardState,
    whenType: initialWhenType,
  }));
  const [step, setStep] = useState<WizardStep>("what");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChange = useCallback((updates: Partial<WizardState>) => {
    setState((prev) => ({ ...prev, ...updates }));
  }, []);

  const handleClose = () => {
    onOpenChange(false);
    // Reset after animation
    setTimeout(() => {
      setState({ ...initialWizardState, whenType: initialWhenType });
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
      if (state.whenType === "recurring") {
        setStep("delivery");
      } else {
        // For "now" and "past", submit directly
        handleSubmit();
      }
    } else if (step === "delivery") {
      handleSubmit();
    }
  };

  const handleBack = () => {
    if (step === "when") {
      setStep("what");
    } else if (step === "delivery") {
      setStep("when");
    }
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      if (state.whenType === "now" && onGenerateNow) {
        await onGenerateNow(state);
      } else if (state.whenType === "recurring" && onCreateSchedule) {
        await onCreateSchedule(state);
      } else if (state.whenType === "past" && onGeneratePast) {
        await onGeneratePast(state);
      }
      handleClose();
    } catch (error) {
      console.error("Wizard submit error:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getSubmitLabel = () => {
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

  const isLastStep =
    step === "delivery" || (step === "when" && state.whenType !== "recurring");

  const canProceed =
    (step === "what" && canProceedFromWhat()) ||
    (step === "when" && canProceedFromWhen()) ||
    step === "delivery";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Summary</DialogTitle>
        </DialogHeader>

        <WizardProgress currentStep={step} whenType={state.whenType} />

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
            {step === "delivery" && (
              <DeliveryStep state={state} onChange={handleChange} guildId={guildId} />
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
