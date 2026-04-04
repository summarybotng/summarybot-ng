/**
 * Debounced Number Input Component (ADR-037)
 *
 * Number input that only submits on blur or Enter to prevent auto-submit while typing.
 * Extracted from SummaryFilters for reuse across filter forms.
 */

import { useState, useEffect, useCallback } from "react";
import { Input } from "@/components/ui/input";

interface DebouncedNumberInputProps {
  value: number | undefined;
  onChange: (value: number | undefined) => void;
  placeholder?: string;
  className?: string;
  min?: number;
  max?: number;
}

export function DebouncedNumberInput({
  value,
  onChange,
  placeholder,
  className,
  min,
  max,
}: DebouncedNumberInputProps) {
  const [localValue, setLocalValue] = useState(value?.toString() ?? "");

  // Sync local value when external value changes
  useEffect(() => {
    setLocalValue(value?.toString() ?? "");
  }, [value]);

  const handleCommit = useCallback(() => {
    const parsed = localValue ? parseInt(localValue, 10) : undefined;
    if (parsed !== value) {
      onChange(parsed);
    }
  }, [localValue, value, onChange]);

  return (
    <Input
      type="number"
      placeholder={placeholder}
      className={className}
      min={min}
      max={max}
      value={localValue}
      onChange={(e) => setLocalValue(e.target.value)}
      onBlur={handleCommit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          handleCommit();
        }
      }}
    />
  );
}
