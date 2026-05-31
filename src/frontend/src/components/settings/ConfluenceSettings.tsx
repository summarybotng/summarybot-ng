/**
 * Confluence Settings Component (ADR-099)
 *
 * Per-tenant Confluence configuration for publishing summaries.
 * Admin-only settings for connecting to Atlassian Confluence.
 */

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  useConfluenceSettings,
  useUpdateConfluenceSettings,
  useDeleteConfluenceSettings,
  useTestConfluenceConnection,
  type ConfluenceSettingsRequest,
} from "@/hooks/useConfluencePublish";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useToast } from "@/hooks/use-toast";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  FileText,
  Key,
  Loader2,
  Settings,
  Trash2,
  Unlink,
} from "lucide-react";

interface ConfluenceSettingsProps {
  guildId: string;
  animationDelay?: number;
}

export function ConfluenceSettings({
  guildId,
  animationDelay = 0.4,
}: ConfluenceSettingsProps) {
  const { toast } = useToast();
  const [showConfigDialog, setShowConfigDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  // Form state
  const [formData, setFormData] = useState<ConfluenceSettingsRequest>({
    enabled: false,
    base_url: "",
    space_key: "",
    parent_page_id: null,
    email: "",
    api_token: null,
    page_title_template: "{title}",
    // ADR-113: Section toggles
    include_summary: true,
    include_key_points: true,
    include_action_items: true,
    include_participants: false,
    include_labels: true,
    // ADR-114: Page Properties toggles
    include_page_properties: true,
    page_properties_in_expander: true,
    prop_show_channel: true,
    prop_show_period_start: true,
    prop_show_period_end: true,
    prop_show_message_count: true,
    prop_show_participant_count: false,  // Off by default
    prop_show_summary_type: true,
    prop_show_perspective: true,  // On by default
    prop_show_granularity: true,
    prop_show_source: true,  // On by default
  });

  // Queries & Mutations
  const { data: settings, isLoading, isError, error, refetch } = useConfluenceSettings(guildId);
  const updateSettings = useUpdateConfluenceSettings(guildId);
  const deleteSettings = useDeleteConfluenceSettings(guildId);
  const testConnection = useTestConfluenceConnection(guildId);

  // Initialize form when settings load
  useEffect(() => {
    if (settings) {
      setFormData({
        enabled: settings.enabled,
        base_url: settings.base_url || "",
        space_key: settings.space_key || "",
        parent_page_id: settings.parent_page_id || null,
        email: settings.email || "",
        api_token: null, // Don't pre-fill token
        page_title_template: settings.page_title_template || "{title}",
        // ADR-113: Section toggles (with defaults for existing data)
        include_summary: settings.include_summary ?? true,
        include_key_points: settings.include_key_points ?? true,
        include_action_items: settings.include_action_items ?? true,
        include_participants: settings.include_participants ?? false,
        include_labels: settings.include_labels ?? true,
        // ADR-114: Page Properties toggles (with defaults for existing data)
        include_page_properties: settings.include_page_properties ?? true,
        page_properties_in_expander: settings.page_properties_in_expander ?? true,
        prop_show_channel: settings.prop_show_channel ?? true,
        prop_show_period_start: settings.prop_show_period_start ?? true,
        prop_show_period_end: settings.prop_show_period_end ?? true,
        prop_show_message_count: settings.prop_show_message_count ?? true,
        prop_show_participant_count: settings.prop_show_participant_count ?? false,  // Off by default
        prop_show_summary_type: settings.prop_show_summary_type ?? true,
        prop_show_perspective: settings.prop_show_perspective ?? true,  // On by default
        prop_show_granularity: settings.prop_show_granularity ?? true,
        prop_show_source: settings.prop_show_source ?? true,  // On by default
      });
    }
  }, [settings]);

  const handleSave = async () => {
    try {
      await updateSettings.mutateAsync(formData);
      toast({
        title: "Settings saved",
        description: "Confluence configuration has been updated.",
      });
      setShowConfigDialog(false);
      refetch();
    } catch (error) {
      toast({
        title: "Failed to save settings",
        description: error instanceof Error ? error.message : "Please try again",
        variant: "destructive",
      });
    }
  };

  const handleTest = async () => {
    try {
      const result = await testConnection.mutateAsync();
      toast({
        title: "Connection successful",
        description: result.message || `Connected to space "${result.space_name}"`,
      });
    } catch (error) {
      toast({
        title: "Connection failed",
        description: error instanceof Error ? error.message : "Check your settings",
        variant: "destructive",
      });
    }
  };

  const handleDelete = async () => {
    try {
      await deleteSettings.mutateAsync();
      toast({
        title: "Settings removed",
        description: "Confluence configuration has been deleted.",
      });
      setShowDeleteDialog(false);
      refetch();
    } catch (error) {
      toast({
        title: "Failed to delete settings",
        description: error instanceof Error ? error.message : "Please try again",
        variant: "destructive",
      });
    }
  };

  if (isLoading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: animationDelay }}
      >
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-3">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              <span className="text-muted-foreground">Loading Confluence settings...</span>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  // Show card even on error - allows user to try configuring
  const isConfigured = settings?.is_configured || false;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: animationDelay }}
    >
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <FileText className="h-5 w-5 text-blue-500" />
              <div>
                <CardTitle className="text-lg">Confluence Integration</CardTitle>
                <CardDescription>
                  Publish summaries to Atlassian Confluence
                </CardDescription>
              </div>
            </div>
            {isConfigured ? (
              <Badge variant="outline" className="border-green-500/50 text-green-600">
                <CheckCircle2 className="mr-1 h-3 w-3" />
                Connected
              </Badge>
            ) : (
              <Badge variant="outline" className="text-muted-foreground">
                Not configured
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Show error if API failed but still render the card */}
          {isError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                Failed to load settings: {error instanceof Error ? error.message : "Unknown error"}
              </AlertDescription>
            </Alert>
          )}

          {isConfigured ? (
            <>
              {/* Connection Info */}
              <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
                <div className="grid gap-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Instance URL</span>
                    <a
                      href={settings?.base_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-primary hover:underline"
                    >
                      {settings?.base_url?.replace(/^https?:\/\//, "")}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Space</span>
                    <span className="font-medium">{settings?.space_key}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Email</span>
                    <span className="font-medium">{settings?.email}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">API Token</span>
                    <span className="flex items-center gap-1">
                      <Key className="h-3 w-3" />
                      {settings?.has_api_token ? "Configured" : "Not set"}
                    </span>
                  </div>
                  {settings?.enabled === false && (
                    <Alert variant="destructive" className="mt-2">
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription>
                        Publishing is currently disabled
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleTest}
                  disabled={testConnection.isPending}
                >
                  {testConnection.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                  )}
                  Test Connection
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowConfigDialog(true)}
                >
                  <Settings className="mr-2 h-4 w-4" />
                  Edit Settings
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowDeleteDialog(true)}
                  className="text-destructive hover:text-destructive"
                >
                  <Unlink className="mr-2 h-4 w-4" />
                  Disconnect
                </Button>
              </div>
            </>
          ) : (
            <>
              {/* Not Configured */}
              <div className="text-sm text-muted-foreground space-y-2">
                <p>
                  Connect your Atlassian Confluence to publish summaries as wiki pages.
                  You'll need:
                </p>
                <ul className="list-disc list-inside ml-2 space-y-1">
                  <li>Your Confluence instance URL (e.g., company.atlassian.net)</li>
                  <li>A space key where pages will be created</li>
                  <li>An API token from{" "}
                    <a
                      href="https://id.atlassian.com/manage-profile/security/api-tokens"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline"
                    >
                      id.atlassian.com
                    </a>
                  </li>
                </ul>
              </div>
              <Button onClick={() => setShowConfigDialog(true)}>
                <Settings className="mr-2 h-4 w-4" />
                Configure Confluence
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      {/* Configuration Dialog */}
      <Dialog open={showConfigDialog} onOpenChange={setShowConfigDialog}>
        <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Confluence Settings</DialogTitle>
            <DialogDescription>
              Configure your Atlassian Confluence connection for publishing summaries.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {/* Enabled Toggle */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="enabled">Enable Publishing</Label>
                <p className="text-xs text-muted-foreground">
                  Allow publishing summaries to Confluence
                </p>
              </div>
              <Switch
                id="enabled"
                checked={formData.enabled}
                onCheckedChange={(checked) =>
                  setFormData((prev) => ({ ...prev, enabled: checked }))
                }
              />
            </div>

            {/* Base URL */}
            <div className="grid gap-2">
              <Label htmlFor="base_url">Instance URL</Label>
              <Input
                id="base_url"
                placeholder="https://company.atlassian.net"
                value={formData.base_url}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, base_url: e.target.value }))
                }
              />
              <p className="text-xs text-muted-foreground">
                Your Confluence Cloud or Data Center URL
              </p>
            </div>

            {/* Space Key */}
            <div className="grid gap-2">
              <Label htmlFor="space_key">Space Key</Label>
              <Input
                id="space_key"
                placeholder="TEAM"
                value={formData.space_key}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    space_key: e.target.value.toUpperCase(),
                  }))
                }
              />
              <p className="text-xs text-muted-foreground">
                The space where pages will be created
              </p>
            </div>

            {/* Parent Page ID */}
            <div className="grid gap-2">
              <Label htmlFor="parent_page_id">Parent Page ID (Optional)</Label>
              <Input
                id="parent_page_id"
                placeholder="123456789"
                value={formData.parent_page_id || ""}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    parent_page_id: e.target.value || null,
                  }))
                }
              />
              <p className="text-xs text-muted-foreground">
                Optional: Create pages under a specific parent page
              </p>
            </div>

            {/* Email */}
            <div className="grid gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="service@company.com"
                value={formData.email}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, email: e.target.value }))
                }
              />
              <p className="text-xs text-muted-foreground">
                Email associated with your API token
              </p>
            </div>

            {/* API Token */}
            <div className="grid gap-2">
              <Label htmlFor="api_token">API Token</Label>
              <Input
                id="api_token"
                type="password"
                placeholder={settings?.has_api_token ? "••••••••••••••••" : "Enter API token"}
                value={formData.api_token || ""}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    api_token: e.target.value || null,
                  }))
                }
              />
              <p className="text-xs text-muted-foreground">
                {settings?.has_api_token
                  ? "Leave empty to keep existing token"
                  : "Generate at id.atlassian.com"}
              </p>
            </div>

            {/* Page Title Template */}
            <div className="grid gap-2">
              <Label htmlFor="page_title_template">Page Title Template</Label>
              <Input
                id="page_title_template"
                placeholder="{title}"
                value={formData.page_title_template || "{title}"}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    page_title_template: e.target.value,
                  }))
                }
              />
              <p className="text-xs text-muted-foreground">
                Use {"{title}"} for summary title
              </p>
            </div>

            {/* ADR-113: Section Toggles */}
            <div className="grid gap-3 pt-4 border-t">
              <Label className="text-sm font-medium">Page Sections</Label>
              <p className="text-xs text-muted-foreground -mt-1">
                Choose which sections to include when publishing to Confluence
              </p>

              <div className="flex items-center justify-between">
                <Label htmlFor="include_summary" className="text-sm font-normal cursor-pointer">
                  Summary
                </Label>
                <Switch
                  id="include_summary"
                  checked={formData.include_summary ?? true}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({ ...prev, include_summary: checked }))
                  }
                />
              </div>

              <div className="flex items-center justify-between">
                <Label htmlFor="include_key_points" className="text-sm font-normal cursor-pointer">
                  Key Points
                </Label>
                <Switch
                  id="include_key_points"
                  checked={formData.include_key_points ?? true}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({ ...prev, include_key_points: checked }))
                  }
                />
              </div>

              <div className="flex items-center justify-between">
                <Label htmlFor="include_action_items" className="text-sm font-normal cursor-pointer">
                  Action Items
                </Label>
                <Switch
                  id="include_action_items"
                  checked={formData.include_action_items ?? true}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({ ...prev, include_action_items: checked }))
                  }
                />
              </div>

              <div className="flex items-center justify-between">
                <Label htmlFor="include_participants" className="text-sm font-normal cursor-pointer">
                  Participants
                </Label>
                <Switch
                  id="include_participants"
                  checked={formData.include_participants ?? false}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({ ...prev, include_participants: checked }))
                  }
                />
              </div>
            </div>

            {/* ADR-113: Labels Toggle */}
            <div className="grid gap-3 pt-4 border-t">
              <Label className="text-sm font-medium">Page Labels</Label>
              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="include_labels" className="text-sm font-normal cursor-pointer">
                    Add labels to pages
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Adds channel, scope, and category labels
                  </p>
                </div>
                <Switch
                  id="include_labels"
                  checked={formData.include_labels ?? true}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({ ...prev, include_labels: checked }))
                  }
                />
              </div>
            </div>

            {/* ADR-114: Page Properties Toggle */}
            <div className="grid gap-3 pt-4 border-t">
              <Label className="text-sm font-medium">Page Properties</Label>
              <p className="text-xs text-muted-foreground -mt-1">
                Queryable metadata table for Page Properties Reports
              </p>

              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="include_page_properties" className="text-sm font-normal cursor-pointer">
                    Include Page Properties
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Adds a queryable properties table
                  </p>
                </div>
                <Switch
                  id="include_page_properties"
                  checked={formData.include_page_properties ?? true}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({ ...prev, include_page_properties: checked }))
                  }
                />
              </div>

              {formData.include_page_properties && (
                <>
                  <div className="flex items-center justify-between pl-4">
                    <Label htmlFor="page_properties_in_expander" className="text-sm font-normal cursor-pointer">
                      Wrap in expander
                    </Label>
                    <Switch
                      id="page_properties_in_expander"
                      checked={formData.page_properties_in_expander ?? true}
                      onCheckedChange={(checked) =>
                        setFormData((prev) => ({ ...prev, page_properties_in_expander: checked }))
                      }
                    />
                  </div>

                  <div className="pl-4">
                    <p className="text-xs text-muted-foreground mb-2">Properties to include:</p>

                    <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="prop_show_channel" className="text-xs font-normal cursor-pointer">
                          Channel
                        </Label>
                        <Switch
                          id="prop_show_channel"
                          checked={formData.prop_show_channel ?? true}
                          onCheckedChange={(checked) =>
                            setFormData((prev) => ({ ...prev, prop_show_channel: checked }))
                          }
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="prop_show_message_count" className="text-xs font-normal cursor-pointer">
                          Messages
                        </Label>
                        <Switch
                          id="prop_show_message_count"
                          checked={formData.prop_show_message_count ?? true}
                          onCheckedChange={(checked) =>
                            setFormData((prev) => ({ ...prev, prop_show_message_count: checked }))
                          }
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="prop_show_period_start" className="text-xs font-normal cursor-pointer">
                          Period Start
                        </Label>
                        <Switch
                          id="prop_show_period_start"
                          checked={formData.prop_show_period_start ?? true}
                          onCheckedChange={(checked) =>
                            setFormData((prev) => ({ ...prev, prop_show_period_start: checked }))
                          }
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="prop_show_participant_count" className="text-xs font-normal cursor-pointer text-muted-foreground">
                          Participants
                        </Label>
                        <Switch
                          id="prop_show_participant_count"
                          checked={formData.prop_show_participant_count ?? false}
                          onCheckedChange={(checked) =>
                            setFormData((prev) => ({ ...prev, prop_show_participant_count: checked }))
                          }
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="prop_show_period_end" className="text-xs font-normal cursor-pointer">
                          Period End
                        </Label>
                        <Switch
                          id="prop_show_period_end"
                          checked={formData.prop_show_period_end ?? true}
                          onCheckedChange={(checked) =>
                            setFormData((prev) => ({ ...prev, prop_show_period_end: checked }))
                          }
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="prop_show_summary_type" className="text-xs font-normal cursor-pointer">
                          Summary Type
                        </Label>
                        <Switch
                          id="prop_show_summary_type"
                          checked={formData.prop_show_summary_type ?? true}
                          onCheckedChange={(checked) =>
                            setFormData((prev) => ({ ...prev, prop_show_summary_type: checked }))
                          }
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="prop_show_granularity" className="text-xs font-normal cursor-pointer">
                          Granularity
                        </Label>
                        <Switch
                          id="prop_show_granularity"
                          checked={formData.prop_show_granularity ?? true}
                          onCheckedChange={(checked) =>
                            setFormData((prev) => ({ ...prev, prop_show_granularity: checked }))
                          }
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="prop_show_perspective" className="text-xs font-normal cursor-pointer">
                          Perspective
                        </Label>
                        <Switch
                          id="prop_show_perspective"
                          checked={formData.prop_show_perspective ?? true}
                          onCheckedChange={(checked) =>
                            setFormData((prev) => ({ ...prev, prop_show_perspective: checked }))
                          }
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label htmlFor="prop_show_source" className="text-xs font-normal cursor-pointer">
                          Source
                        </Label>
                        <Switch
                          id="prop_show_source"
                          checked={formData.prop_show_source ?? true}
                          onCheckedChange={(checked) =>
                            setFormData((prev) => ({ ...prev, prop_show_source: checked }))
                          }
                        />
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowConfigDialog(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={updateSettings.isPending}
            >
              {updateSettings.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Save Settings
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disconnect Confluence?</AlertDialogTitle>
            <AlertDialogDescription>
              This will remove the Confluence configuration. You won't be able to
              publish summaries until you reconfigure it. Previously published
              pages will remain in Confluence.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteSettings.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" />
              )}
              Disconnect
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </motion.div>
  );
}
