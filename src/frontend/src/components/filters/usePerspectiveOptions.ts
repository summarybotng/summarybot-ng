/**
 * Hook for combining system and custom perspectives (ADR-037)
 *
 * Provides a unified list of perspective options for filter dropdowns,
 * combining built-in system perspectives with guild-specific custom templates.
 */

import { useMemo } from "react";
import { useDefaultPrompts } from "@/hooks/usePrompts";
import { usePromptTemplates } from "@/hooks/usePromptTemplates";
import type { PerspectiveOption } from "./FilterCriteriaForm";

interface UsePerspectiveOptionsReturn {
  perspectives: PerspectiveOption[];
  isLoading: boolean;
}

/**
 * Get combined perspective options from system defaults and guild custom templates.
 * @param guildId - Guild ID for fetching custom templates (optional)
 */
export function usePerspectiveOptions(guildId?: string): UsePerspectiveOptionsReturn {
  const { data: defaultPrompts, isLoading: loadingDefaults } = useDefaultPrompts();
  const { data: customTemplates, isLoading: loadingTemplates } = usePromptTemplates(guildId || "");

  const perspectives = useMemo(() => {
    const options: PerspectiveOption[] = [];

    // Add system perspectives from default prompts
    if (defaultPrompts?.perspectives) {
      Object.keys(defaultPrompts.perspectives).forEach((key) => {
        options.push({
          value: key,
          label: key.charAt(0).toUpperCase() + key.slice(1),
          isCustom: false,
        });
      });
    }

    // Add custom templates as perspectives
    if (customTemplates) {
      customTemplates.forEach((template) => {
        // Avoid duplicates if custom template has same name as system perspective
        const exists = options.some(
          (p) => p.value.toLowerCase() === template.name.toLowerCase()
        );
        if (!exists) {
          options.push({
            value: template.name.toLowerCase(),
            label: template.name,
            isCustom: true,
          });
        }
      });
    }

    // Sort: system first, then custom alphabetically
    return options.sort((a, b) => {
      if (a.isCustom !== b.isCustom) {
        return a.isCustom ? 1 : -1;
      }
      return a.label.localeCompare(b.label);
    });
  }, [defaultPrompts, customTemplates]);

  return {
    perspectives,
    isLoading: loadingDefaults || (!!guildId && loadingTemplates),
  };
}
