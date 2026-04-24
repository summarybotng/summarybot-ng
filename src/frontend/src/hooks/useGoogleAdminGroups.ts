/**
 * ADR-050: Hooks for Google Admin Groups
 *
 * Provides query and mutation hooks for managing Google Workspace admin groups
 * that grant admin access to guild members.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { GoogleAdminGroup } from "@/types";

interface GoogleAdminGroupsResponse {
  groups: GoogleAdminGroup[];
}

interface AddGoogleAdminGroupRequest {
  google_group_email: string;
}

/**
 * Fetch all Google admin groups for a guild
 */
export function useGoogleAdminGroups(guildId: string) {
  return useQuery({
    queryKey: ["google-admin-groups", guildId],
    queryFn: () =>
      api.get<GoogleAdminGroupsResponse>(
        `/guilds/${guildId}/google-admin-groups`
      ),
    select: (data) => data.groups,
    enabled: !!guildId,
  });
}

/**
 * Add a Google admin group to a guild
 */
export function useAddGoogleAdminGroup(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: AddGoogleAdminGroupRequest) =>
      api.post<GoogleAdminGroup>(
        `/guilds/${guildId}/google-admin-groups`,
        request
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["google-admin-groups", guildId],
      });
    },
  });
}

/**
 * Remove a Google admin group from a guild
 */
export function useRemoveGoogleAdminGroup(guildId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (groupId: string) =>
      api.delete(`/guilds/${guildId}/google-admin-groups/${groupId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["google-admin-groups", guildId],
      });
    },
  });
}
