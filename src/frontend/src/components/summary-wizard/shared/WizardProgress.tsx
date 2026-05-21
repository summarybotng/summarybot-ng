/**
 * Wizard Progress Indicator (ADR-089)
 */

import { cn } from "@/lib/utils";
import { Check } from "lucide-react";
import type { WizardStep, WhenType } from "../types";

interface WizardProgressProps {
  currentStep: WizardStep;
  whenType: WhenType;
}

export function WizardProgress({ currentStep, whenType }: WizardProgressProps) {
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
            <div
              className={cn(
                "flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium transition-colors",
                isCompleted && "bg-primary text-primary-foreground",
                isCurrent && "bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2",
                !isCompleted && !isCurrent && "bg-muted text-muted-foreground"
              )}
            >
              {isCompleted ? <Check className="w-4 h-4" /> : step.number}
            </div>
            <span
              className={cn(
                "ml-2 text-sm hidden sm:inline",
                isCurrent ? "font-medium" : "text-muted-foreground"
              )}
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
