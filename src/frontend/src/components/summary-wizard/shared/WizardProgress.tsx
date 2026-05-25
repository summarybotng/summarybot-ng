/**
 * Wizard Progress Indicator (ADR-089)
 *
 * Supports free navigation - click any step to jump to it.
 */

import { cn } from "@/lib/utils";
import { Check } from "lucide-react";
import type { WizardStep, WhenType } from "../types";

interface WizardProgressProps {
  currentStep: WizardStep;
  whenType: WhenType;
  onStepClick?: (step: WizardStep) => void;
}

export function WizardProgress({ currentStep, whenType, onStepClick }: WizardProgressProps) {
  // "Where" step is now available for all modes
  const steps = [
    { id: "what" as const, label: "What", number: 1 },
    { id: "when" as const, label: "When", number: 2 },
    { id: "where" as const, label: "Where", number: 3 },
  ];

  const currentIndex = steps.findIndex((s) => s.id === currentStep);

  return (
    <div className="flex items-center justify-center gap-2 mb-6">
      {steps.map((step, index) => {
        const isCompleted = index < currentIndex;
        const isCurrent = step.id === currentStep;
        const isClickable = !!onStepClick;

        return (
          <div key={step.id} className="flex items-center">
            {index > 0 && (
              <div
                className={cn(
                  "w-8 h-0.5 mx-1",
                  isCompleted ? "bg-primary" : "bg-muted"
                )}
              />
            )}
            <button
              type="button"
              onClick={() => onStepClick?.(step.id)}
              disabled={!isClickable}
              className={cn(
                "flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium transition-colors",
                isCompleted && "bg-primary text-primary-foreground",
                isCurrent && "bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2",
                !isCompleted && !isCurrent && "bg-muted text-muted-foreground",
                isClickable && !isCurrent && "hover:ring-2 hover:ring-primary/50 hover:ring-offset-1 cursor-pointer"
              )}
            >
              {isCompleted ? <Check className="w-4 h-4" /> : step.number}
            </button>
            <button
              type="button"
              onClick={() => onStepClick?.(step.id)}
              disabled={!isClickable}
              className={cn(
                "ml-2 text-sm hidden sm:inline",
                isCurrent ? "font-medium" : "text-muted-foreground",
                isClickable && !isCurrent && "hover:text-foreground cursor-pointer"
              )}
            >
              {step.label}
            </button>
          </div>
        );
      })}
    </div>
  );
}
