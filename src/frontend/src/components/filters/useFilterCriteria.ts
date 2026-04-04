/**
 * Filter Criteria Hook (ADR-037)
 *
 * Hook for managing SummaryFilterCriteria state with URL sync and persistence.
 * Used by summary lists, feeds, webhooks, and bulk operations.
 */

import { useState, useCallback, useMemo } from "react";
import type { SummaryFilterCriteria } from "@/types/filters";
import { getDefaultCriteria, clearFilters, countActiveFilters } from "@/types/filters";

interface UseFilterCriteriaOptions {
  /** Initial criteria (overrides defaults) */
  initialCriteria?: Partial<SummaryFilterCriteria>;
  /** Whether to include sort options in the criteria */
  includeSortOptions?: boolean;
}

interface UseFilterCriteriaReturn {
  /** Current filter criteria */
  criteria: SummaryFilterCriteria;
  /** Update criteria with partial values */
  updateCriteria: (updates: Partial<SummaryFilterCriteria>) => void;
  /** Reset criteria to defaults */
  resetCriteria: () => void;
  /** Clear all filters (keeps sort options) */
  clearAllFilters: () => void;
  /** Number of active filters (excluding sort) */
  activeFilterCount: number;
  /** Check if any filters are active */
  hasActiveFilters: boolean;
}

export function useFilterCriteria(
  options: UseFilterCriteriaOptions = {}
): UseFilterCriteriaReturn {
  const { initialCriteria, includeSortOptions = true } = options;

  const defaultCriteria = useMemo(() => {
    const base = getDefaultCriteria();
    if (!includeSortOptions) {
      delete base.sortBy;
      delete base.sortOrder;
    }
    return { ...base, ...initialCriteria };
  }, [initialCriteria, includeSortOptions]);

  const [criteria, setCriteria] = useState<SummaryFilterCriteria>(defaultCriteria);

  const updateCriteria = useCallback((updates: Partial<SummaryFilterCriteria>) => {
    setCriteria((prev) => ({ ...prev, ...updates }));
  }, []);

  const resetCriteria = useCallback(() => {
    setCriteria(defaultCriteria);
  }, [defaultCriteria]);

  const clearAllFilters = useCallback(() => {
    setCriteria((prev) => clearFilters(prev));
  }, []);

  const activeFilterCount = useMemo(() => countActiveFilters(criteria), [criteria]);

  const hasActiveFilters = activeFilterCount > 0;

  return {
    criteria,
    updateCriteria,
    resetCriteria,
    clearAllFilters,
    activeFilterCount,
    hasActiveFilters,
  };
}
