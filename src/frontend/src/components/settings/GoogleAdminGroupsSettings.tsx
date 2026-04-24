/**
 * ADR-050: Google Admin Groups Settings Component
 *
 * Allows admins to configure which Google Workspace groups grant admin access
 * to the guild dashboard. Users who are members of these Google groups will
 * have admin privileges.
 */

import { useState } from "react";
import { motion } from "framer-motion";
import {
  useGoogleAdminGroups,
  useAddGoogleAdminGroup,
  useRemoveGoogleAdminGroup,
} from "@/hooks/useGoogleAdminGroups";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import {
  AlertCircle,
  Loader2,
  Mail,
  Plus,
  Shield,
  Trash2,
  Users,
} from "lucide-react";
import type { GoogleAdminGroup } from "@/types";

interface GoogleAdminGroupsSettingsProps {
  guildId: string;
  animationDelay?: number;
}

export function GoogleAdminGroupsSettings({
  guildId,
  animationDelay = 0.3,
}: GoogleAdminGroupsSettingsProps) {
  const { data: groups, isLoading, error } = useGoogleAdminGroups(guildId);
  const addGroup = useAddGoogleAdminGroup(guildId);
  const removeGroup = useRemoveGoogleAdminGroup(guildId);
  const { toast } = useToast();

  const [newGroupEmail, setNewGroupEmail] = useState("");

  const handleAddGroup = async (e: React.FormEvent) => {
    e.preventDefault();

    const email = newGroupEmail.trim();
    if (!email) {
      toast({
        title: "Error",
        description: "Please enter a Google group email address.",
        variant: "destructive",
      });
      return;
    }

    // Basic email validation
    if (!email.includes("@") || !email.includes(".")) {
      toast({
        title: "Error",
        description: "Please enter a valid email address.",
        variant: "destructive",
      });
      return;
    }

    try {
      await addGroup.mutateAsync({ google_group_email: email });
      setNewGroupEmail("");
      toast({
        title: "Group added",
        description: `${email} has been added as an admin group.`,
      });
    } catch (err) {
      console.error("Failed to add Google admin group:", err);
      const errorMessage =
        err && typeof err === "object" && "error" in err
          ? (err as { error: { message: string } }).error.message
          : "Failed to add Google admin group.";
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
    }
  };

  const handleRemoveGroup = async (group: GoogleAdminGroup) => {
    try {
      await removeGroup.mutateAsync(group.id);
      toast({
        title: "Group removed",
        description: `${group.google_group_email} has been removed from admin groups.`,
      });
    } catch (err) {
      console.error("Failed to remove Google admin group:", err);
      toast({
        title: "Error",
        description: "Failed to remove Google admin group.",
        variant: "destructive",
      });
    }
  };

  if (isLoading) {
    return <GoogleAdminGroupsSkeleton />;
  }

  if (error) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: animationDelay }}
      >
        <Card className="border-destructive/50">
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-destructive" />
              <CardTitle>Google Admin Groups</CardTitle>
            </div>
            <CardDescription className="text-destructive">
              Failed to load Google admin groups. Please try again later.
            </CardDescription>
          </CardHeader>
        </Card>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: animationDelay }}
    >
      <Card className="border-border/50">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            <CardTitle>Google Admin Groups</CardTitle>
          </div>
          <CardDescription>
            Members of these Google Workspace groups will have admin access to
            this guild's dashboard. This allows you to manage access using your
            existing Google Workspace groups.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Add new group form */}
          <form onSubmit={handleAddGroup} className="flex gap-2">
            <div className="relative flex-1">
              <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="email"
                placeholder="admin-group@yourdomain.com"
                value={newGroupEmail}
                onChange={(e) => setNewGroupEmail(e.target.value)}
                className="pl-9"
                disabled={addGroup.isPending}
              />
            </div>
            <Button type="submit" disabled={addGroup.isPending || !newGroupEmail.trim()}>
              {addGroup.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-2 h-4 w-4" />
              )}
              Add Group
            </Button>
          </form>

          {/* Groups list */}
          <div className="space-y-3">
            <label className="text-sm font-medium">Admin Groups</label>

            {(!groups || groups.length === 0) ? (
              <div className="rounded-lg border border-dashed border-border/50 bg-muted/20 p-6 text-center">
                <Users className="mx-auto h-8 w-8 text-muted-foreground/50" />
                <p className="mt-2 text-sm text-muted-foreground">
                  No Google admin groups configured
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Add a Google Workspace group email above to grant admin access
                  to its members.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {groups.map((group) => (
                  <div
                    key={group.id}
                    className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      <Mail className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-sm font-medium">
                          {group.google_group_email}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Added{" "}
                          {new Date(group.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="text-xs">
                        <Shield className="mr-1 h-3 w-3" />
                        Admin
                      </Badge>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveGroup(group)}
                        disabled={removeGroup.isPending}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        {removeGroup.isPending ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Info notice */}
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
            <p className="text-sm font-medium">How it works</p>
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              <li className="flex items-start gap-2">
                <span className="text-primary">1.</span>
                Add a Google Workspace group email address above
              </li>
              <li className="flex items-start gap-2">
                <span className="text-primary">2.</span>
                Members of that group who sign in with Google SSO will be
                granted admin access
              </li>
              <li className="flex items-start gap-2">
                <span className="text-primary">3.</span>
                Changes take effect on the user's next sign-in
              </li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function GoogleAdminGroupsSkeleton() {
  return (
    <Card className="border-border/50">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Skeleton className="h-5 w-5" />
          <Skeleton className="h-6 w-48" />
        </div>
        <Skeleton className="h-4 w-full mt-2" />
        <Skeleton className="h-4 w-3/4" />
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex gap-2">
          <Skeleton className="h-10 flex-1" />
          <Skeleton className="h-10 w-28" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      </CardContent>
    </Card>
  );
}

export default GoogleAdminGroupsSettings;
