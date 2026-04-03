/**
 * ADR-034: Guild Prompt Templates
 * Hooks for managing guild-level prompt templates
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  PromptTemplate,
  CreatePromptTemplateRequest,
  UpdatePromptTemplateRequest,
  PromptTemplateUsage,
} from "@/types";

interface PromptTemplatesResponse {
  templates: PromptTemplate[];
  total: number;
}

/**
 * Fetch all prompt templates for a guild
 */
export function usePromptTemplates(guildId: string) {
  return useQuery({
    queryKey: ["prompt-templates", guildId],
    queryFn: () =>
      api.get<PromptTemplatesResponse>(`/guilds/${guildId}/prompt-templates`),
    select: (data) => data.templates,
    enabled: !!guildId,
  });
}

/**
 * Fetch a single prompt template by ID
 */
export function usePromptTemplate(guildId: string, templateId: string | null) {
  return useQuery({
    queryKey: ["prompt-template", guildId, templateId],
    queryFn: () =>
      api.get<PromptTemplate>(`/guilds/${guildId}/prompt-templates/${templateId}`),
    enabled: !!guildId && !!templateId,
  });
}

/**
 * Create a new prompt template
 */
export function useCreatePromptTemplate(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (template: CreatePromptTemplateRequest) =>
      api.post<PromptTemplate>(`/guilds/${guildId}/prompt-templates`, template),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompt-templates", guildId] });
    },
  });
}

/**
 * Update an existing prompt template
 */
export function useUpdatePromptTemplate(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      templateId,
      template,
    }: {
      templateId: string;
      template: UpdatePromptTemplateRequest;
    }) =>
      api.patch<PromptTemplate>(
        `/guilds/${guildId}/prompt-templates/${templateId}`,
        template
      ),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["prompt-templates", guildId] });
      queryClient.invalidateQueries({
        queryKey: ["prompt-template", guildId, variables.templateId],
      });
    },
  });
}

/**
 * Delete a prompt template
 */
export function useDeletePromptTemplate(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, force = false }: { templateId: string; force?: boolean }) =>
      api.delete(`/guilds/${guildId}/prompt-templates/${templateId}?force=${force}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompt-templates", guildId] });
    },
  });
}

/**
 * Get usage information for a template (which schedules use it)
 */
export function usePromptTemplateUsage(guildId: string, templateId: string | null) {
  return useQuery({
    queryKey: ["prompt-template-usage", guildId, templateId],
    queryFn: () =>
      api.get<PromptTemplateUsage>(
        `/guilds/${guildId}/prompt-templates/${templateId}/usage`
      ),
    enabled: !!guildId && !!templateId,
  });
}

/**
 * Duplicate a prompt template
 */
export function useDuplicatePromptTemplate(guildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      templateId,
      newName,
    }: {
      templateId: string;
      newName: string;
    }) =>
      api.post<PromptTemplate>(
        `/guilds/${guildId}/prompt-templates/${templateId}/duplicate`,
        { new_name: newName }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompt-templates", guildId] });
    },
  });
}
