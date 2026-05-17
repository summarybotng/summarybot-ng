/**
 * Google Drive Sync Settings Component
 *
 * ADR-007: Per-Server Google Drive Sync
 * ADR-091: Sync Export Configuration
 *
 * ## Per-Tenant Model
 *
 * Each Discord server (tenant) can configure their own Google Drive:
 * - Server admins authenticate via OAuth with their own Google account
 * - Files sync to Shared Drives only (My Drive disabled for data ownership)
 * - Export settings are per-server (folder structure, JSON toggle)
 *
 * If no custom Drive is configured, the server uses the bot operator's
 * global fallback Drive (service account), with files in a subfolder.
 *
 * ## Shared Drive Requirement
 *
 * For tenanted servers, only Shared Drives are allowed because:
 * - Data ownership: My Drive is personal; if admin leaves, data is lost
 * - Team access: Shared Drives provide org-wide access control
 * - Compliance: Data stays in org-controlled storage
 * - Continuity: Admin changes don't disrupt sync
 *
 * ## UI Location
 *
 * Moved from Retrospective/Archive page to Settings for better UX -
 * sync configuration is a settings concern, not a retrospective action.
 */

import { useState, useEffect } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  useSyncStatus,
  useDriveStatus,
  useOAuthConfig,
  useServerSyncConfig,
  useSyncStats,
  useStartOAuth,
  useDisconnectDrive,
  useConfigureServerSync,
  useTriggerSync,
  useSampleSync,
  useSyncPreview,
  useDriveFolders,
  useSharedDrives,
  useDriveUserInfo,
  useUpdateExportSettings,
} from "@/hooks/useArchive";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useToast } from "@/hooks/use-toast";
import {
  AlertTriangle,
  Briefcase,
  CheckCircle2,
  ChevronRight,
  Cloud,
  CloudOff,
  ExternalLink,
  Files,
  Folder,
  HardDrive,
  HelpCircle,
  Link as LinkIcon,
  Loader2,
  RefreshCw,
  Settings,
  Settings2,
  Unlink,
} from "lucide-react";

interface GoogleDriveSyncSettingsProps {
  guildId: string;
  animationDelay?: number;
}

export function GoogleDriveSyncSettings({
  guildId,
  animationDelay = 0.3,
}: GoogleDriveSyncSettingsProps) {
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const [showSyncPreview, setShowSyncPreview] = useState(false);
  // ADR-091: Default to shared drives for tenanted servers (My Drive disabled)
  const [driveType, setDriveType] = useState<"my_drive" | "shared">("shared");
  const [selectedDriveId, setSelectedDriveId] = useState<string | null>(null);
  const [selectedDriveName, setSelectedDriveName] = useState<string>("My Drive");
  const [folderPath, setFolderPath] = useState<{ id: string; name: string }[]>([
    { id: "root", name: "My Drive" },
  ]);

  // Queries
  const { data: syncStatus, isLoading: syncStatusLoading } = useSyncStatus();
  const { data: driveStatus } = useDriveStatus();
  const { data: oauthConfig } = useOAuthConfig();
  const { data: serverConfig, refetch: refetchServerConfig } = useServerSyncConfig(guildId);
  const { data: sharedDrivesData } = useSharedDrives(guildId);
  const { data: userInfo } = useDriveUserInfo(guildId);
  const { data: syncStats, refetch: refetchSyncStats } = useSyncStats(guildId);
  const { data: foldersData, isLoading: foldersLoading } = useDriveFolders(
    guildId,
    folderPath[folderPath.length - 1]?.id || "root",
    driveType === "shared" ? selectedDriveId || undefined : undefined
  );

  // Handle OAuth redirect
  useEffect(() => {
    const oauthResult = searchParams.get("oauth");
    const selectFolder = searchParams.get("select_folder");

    if (oauthResult === "success") {
      searchParams.delete("oauth");
      searchParams.delete("select_folder");
      setSearchParams(searchParams, { replace: true });

      refetchServerConfig();
      toast({
        title: "Google Drive connected",
        description: "Now select a folder for your archive.",
      });

      if (selectFolder === "true") {
        setShowFolderPicker(true);
      }
    } else if (oauthResult === "error") {
      const message = searchParams.get("message") || "Authorization failed";
      searchParams.delete("oauth");
      searchParams.delete("message");
      setSearchParams(searchParams, { replace: true });

      toast({
        title: "Connection failed",
        description: message,
        variant: "destructive",
      });
    }
  }, [searchParams, setSearchParams, refetchServerConfig, toast]);

  // Build Google Drive folder URL
  const getFolderUrl = (folderId?: string, driveId?: string) => {
    if (!folderId) return null;
    return `https://drive.google.com/drive/folders/${folderId}`;
  };

  // Sync preview for sample sync feature
  const { data: syncPreview, isLoading: previewLoading, error: previewError } = useSyncPreview(
    guildId,
    3 // Preview 3 most recent
  );

  // Mutations
  const startOAuth = useStartOAuth();
  const disconnectDrive = useDisconnectDrive();
  const configureSync = useConfigureServerSync();
  const triggerSync = useTriggerSync();
  const sampleSync = useSampleSync();
  const updateExportSettings = useUpdateExportSettings(guildId);

  const handleConnectDrive = async () => {
    try {
      const result = await startOAuth.mutateAsync({
        serverId: guildId,
        userId: "dashboard_user",
      });
      window.location.href = result.auth_url;
    } catch (error) {
      toast({
        title: "Failed to start authorization",
        description: "Please try again",
        variant: "destructive",
      });
    }
  };

  const handleDisconnect = async () => {
    try {
      await disconnectDrive.mutateAsync(guildId);
      toast({
        title: "Disconnected",
        description: "Google Drive has been disconnected",
      });
      refetchServerConfig();
    } catch {
      toast({
        title: "Failed to disconnect",
        variant: "destructive",
      });
    }
  };

  const handleSelectFolder = async (folderId: string, folderName: string) => {
    if (folderId === "root") {
      toast({
        title: "Invalid selection",
        description: "Please select a specific folder, not the drive root.",
        variant: "destructive",
      });
      return;
    }

    try {
      const pathString = folderPath.map((f) => f.name).join(" / ");
      await configureSync.mutateAsync({
        serverId: guildId,
        folderId,
        folderName,
        folderPath: pathString + " / " + folderName,
        driveType,
        driveId: driveType === "shared" ? selectedDriveId || undefined : undefined,
        driveName: selectedDriveName,
      });
      toast({
        title: "Folder configured",
        description: `Archives will sync to "${folderName}" in ${selectedDriveName}`,
      });
      setShowFolderPicker(false);
      refetchServerConfig();
    } catch (error) {
      toast({
        title: "Failed to configure folder",
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    }
  };

  const handleTriggerSync = async () => {
    try {
      const result = await triggerSync.mutateAsync(`discord:${guildId}`);
      toast({
        title: "Sync complete",
        description: `Synced ${result.files_synced} files`,
      });
      refetchSyncStats();
    } catch {
      toast({
        title: "Sync failed",
        variant: "destructive",
      });
    }
  };

  // ADR-091: Sample sync - sync 3 most recent files for preview
  const handleSampleSync = async () => {
    try {
      const result = await sampleSync.mutateAsync({
        sourceKey: `discord:${guildId}`,
        sampleSize: 3,
      });
      toast({
        title: "Sample sync complete",
        description: `Synced ${result.files_synced} sample files. Check your Drive to verify the folder structure.`,
      });
      refetchSyncStats();
      setShowSyncPreview(false);
    } catch {
      toast({
        title: "Sample sync failed",
        variant: "destructive",
      });
    }
  };

  const navigateToFolder = (folderId: string, folderName: string) => {
    setFolderPath([...folderPath, { id: folderId, name: folderName }]);
  };

  const navigateBack = (index: number) => {
    setFolderPath(folderPath.slice(0, index + 1));
  };

  const handleDriveTypeChange = (
    type: "my_drive" | "shared",
    driveId?: string,
    driveName?: string
  ) => {
    setDriveType(type);
    if (type === "my_drive") {
      setSelectedDriveId(null);
      setSelectedDriveName("My Drive");
      setFolderPath([{ id: "root", name: "My Drive" }]);
    } else if (driveId && driveName) {
      setSelectedDriveId(driveId);
      setSelectedDriveName(driveName);
      setFolderPath([{ id: driveId, name: driveName }]);
    }
  };

  if (syncStatusLoading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: animationDelay }}
      >
        <Card className="border-border/50">
          <CardContent className="p-6">
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading sync settings...
            </div>
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: animationDelay }}
      className="space-y-4"
    >
      {/* Main Google Drive Sync Card */}
      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="h-5 w-5" />
            Google Drive Sync
          </CardTitle>
          <CardDescription>
            Sync your archive summaries to Google Drive for backup and sharing
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Connection Status */}
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div className="flex items-center gap-3">
              {serverConfig?.enabled && !serverConfig.using_fallback ? (
                <Cloud className="h-8 w-8 text-green-500" />
              ) : syncStatus?.configured ? (
                <Cloud className="h-8 w-8 text-blue-500" />
              ) : (
                <CloudOff className="h-8 w-8 text-muted-foreground" />
              )}
              <div>
                <p className="font-medium">
                  {serverConfig?.enabled && !serverConfig.using_fallback
                    ? "Custom Drive Connected"
                    : syncStatus?.configured
                    ? "Using Default Drive"
                    : "Not Connected"}
                </p>
                {serverConfig?.enabled && !serverConfig.using_fallback ? (
                  <div className="text-sm text-muted-foreground space-y-0.5">
                    <p>
                      Connected as:{" "}
                      {userInfo?.email ||
                        serverConfig.user_email ||
                        "(reconnect to see email)"}
                    </p>
                    <p>
                      Drive: {serverConfig.drive_name || "My Drive"}
                      {serverConfig.drive_type === "shared" && (
                        <Badge variant="outline" className="ml-2 text-xs">
                          Shared
                        </Badge>
                      )}
                    </p>
                    <p className="flex items-center gap-1">
                      Folder:{" "}
                      {serverConfig.folder_id ? (
                        <a
                          href={getFolderUrl(
                            serverConfig.folder_id,
                            serverConfig.drive_id
                          )}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline inline-flex items-center gap-1"
                        >
                          {serverConfig.folder_path ||
                            serverConfig.folder_name ||
                            serverConfig.folder_id}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        serverConfig.folder_path ||
                        serverConfig.folder_name ||
                        "Not set"
                      )}
                    </p>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {syncStatus?.configured
                      ? "Archives sync to the bot operator's Drive"
                      : "Connect Google Drive to enable backup"}
                  </p>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              {serverConfig?.enabled && !serverConfig.using_fallback ? (
                <div className="flex gap-2">
                  {/* ADR-091: Sample sync button for preview */}
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowSyncPreview(true)}
                          disabled={sampleSync.isPending}
                        >
                          {sampleSync.isPending ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          ) : (
                            <Files className="mr-2 h-4 w-4" />
                          )}
                          Sample (3)
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Sync 3 files to preview folder structure</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  {/* Full sync button */}
                  <Button
                    variant="default"
                    size="sm"
                    onClick={handleTriggerSync}
                    disabled={triggerSync.isPending}
                  >
                    {triggerSync.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCw className="mr-2 h-4 w-4" />
                    )}
                    Sync All ({syncStats?.summaries_available || 0})
                  </Button>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleDisconnect}
                    disabled={disconnectDrive.isPending}
                  >
                    <Unlink className="h-4 w-4" />
                  </Button>
                </div>
              ) : oauthConfig?.configured ? (
                <Button onClick={handleConnectDrive} disabled={startOAuth.isPending}>
                  {startOAuth.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <LinkIcon className="mr-2 h-4 w-4" />
                  )}
                  Connect Your Drive
                </Button>
              ) : syncStatus?.configured ? (
                <Badge variant="secondary">Using Fallback</Badge>
              ) : (
                <Badge variant="outline">OAuth Not Configured</Badge>
              )}
            </div>
          </div>

          {/* Last Sync Info */}
          {serverConfig?.last_sync && (
            <div className="text-sm text-muted-foreground">
              Last synced: {new Date(serverConfig.last_sync).toLocaleString()}
            </div>
          )}

          {/* Sync Statistics */}
          {serverConfig?.enabled && !serverConfig.using_fallback && syncStats && (
            <div className="border rounded-lg p-4 bg-muted/30 space-y-2">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <Files className="h-4 w-4" />
                Sync Statistics
              </h4>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Summaries available to sync</p>
                  <p className="font-medium flex items-center gap-2">
                    {syncStats.summaries_available}
                    <Link
                      to={`/guilds/${guildId}/summaries?source=archive`}
                      className="text-primary hover:underline text-xs"
                    >
                      View summaries
                    </Link>
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Files in Drive folder</p>
                  <p className="font-medium flex items-center gap-2">
                    {syncStats.files_in_drive}
                    {serverConfig.folder_id && (
                      <a
                        href={getFolderUrl(serverConfig.folder_id, serverConfig.drive_id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline text-xs inline-flex items-center gap-1"
                      >
                        Open Drive <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </p>
                </div>
              </div>
              {syncStats.summaries_available !== syncStats.files_in_drive && (
                <p className="text-xs text-amber-600 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {syncStats.summaries_available > syncStats.files_in_drive
                    ? `${syncStats.summaries_available - syncStats.files_in_drive} summaries not yet synced. Click "Sync All" to upload.`
                    : "Drive has more files than expected (may include subfolders or manual uploads)."}
                </p>
              )}
            </div>
          )}

          {/* Export Settings */}
          {serverConfig?.enabled && !serverConfig.using_fallback && (
            <div className="border rounded-lg p-4 space-y-4">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <Settings2 className="h-4 w-4" />
                Export Settings
              </h4>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs">Folder Structure</Label>
                  <Select
                    value={serverConfig.folder_structure || "by-period"}
                    onValueChange={(value) => {
                      updateExportSettings.mutate({
                        folder_structure: value as "flat" | "by-period" | "by-channel",
                      });
                    }}
                  >
                    <SelectTrigger className="h-8 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="flat">Flat (all in one folder)</SelectItem>
                      <SelectItem value="by-period">By Period (recommended)</SelectItem>
                      <SelectItem value="by-channel">By Channel</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {(serverConfig.folder_structure || "by-period") === "by-period" && (
                  <div className="space-y-2">
                    <Label className="text-xs">Period Grouping</Label>
                    <Select
                      value={serverConfig.period_grouping || "week"}
                      onValueChange={(value) => {
                        updateExportSettings.mutate({
                          period_grouping: value as "week" | "month",
                        });
                      }}
                    >
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="week">
                          Weekly (e.g., 2026-05-05--2026-05-11)
                        </SelectItem>
                        <SelectItem value="month">
                          Monthly (e.g., 2026-05-01--2026-05-31)
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="include-json"
                  checked={serverConfig.include_json || false}
                  onCheckedChange={(checked) => {
                    updateExportSettings.mutate({ include_json: checked });
                  }}
                />
                <Label htmlFor="include-json" className="text-sm">
                  Include JSON backup files
                </Label>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <HelpCircle className="h-4 w-4 text-muted-foreground" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      JSON files contain complete data for import/restoration. Markdown
                      files are always included for human readability.
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <p className="text-xs text-muted-foreground">
                Files organized in: conversations/
                {serverConfig.period_grouping === "month"
                  ? "YYYY-MM-DD--YYYY-MM-DD"
                  : "weekly date ranges"}
                /
              </p>
            </div>
          )}

          {/* Folder Selection Dialog */}
          {oauthConfig?.configured && !serverConfig?.enabled && (
            <Dialog open={showFolderPicker} onOpenChange={setShowFolderPicker}>
              <DialogTrigger asChild>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => setShowFolderPicker(true)}
                >
                  <Folder className="mr-2 h-4 w-4" />
                  Select Folder After Connecting
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-lg">
                <DialogHeader>
                  <DialogTitle>Select Sync Destination</DialogTitle>
                  <DialogDescription>
                    Choose a drive and folder for your archive summaries
                  </DialogDescription>
                </DialogHeader>

                {/* Drive Type Selection - ADR-091: My Drive disabled for tenanted servers */}
                <div className="space-y-3">
                  <Label className="text-sm font-medium">Step 1: Choose a Shared Drive</Label>

                  {/* Warning about Shared Drive requirement */}
                  <div className="flex items-start gap-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-sm">
                    <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
                    <div>
                      <p className="font-medium text-amber-700">My Drive is not available for server sync</p>
                      <p className="text-amber-600/80 text-xs mt-1">
                        Shared Drives ensure data ownership stays with your organization,
                        even if the admin who connected changes.
                      </p>
                    </div>
                  </div>

                  {/* Shared Drives List */}
                  {sharedDrivesData?.drives?.length ? (
                    <div className="border rounded-lg max-h-40 overflow-y-auto">
                      {sharedDrivesData.drives.map((drive) => (
                        <button
                          key={drive.id}
                          className={`w-full flex items-center gap-2 p-3 hover:bg-muted/50 border-b last:border-b-0 text-left ${
                            selectedDriveId === drive.id ? "bg-primary/10" : ""
                          }`}
                          onClick={() =>
                            handleDriveTypeChange("shared", drive.id, drive.name)
                          }
                        >
                          <Briefcase className="h-4 w-4 text-muted-foreground" />
                          <span>{drive.name}</span>
                          {selectedDriveId === drive.id && (
                            <CheckCircle2 className="h-4 w-4 text-primary ml-auto" />
                          )}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="border rounded-lg p-4 text-center text-muted-foreground">
                      <Briefcase className="h-8 w-8 mx-auto mb-2 opacity-50" />
                      <p className="font-medium">No Shared Drives available</p>
                      <p className="text-xs mt-1">
                        Ask your Google Workspace admin to create a Shared Drive
                        and add you as a member.
                      </p>
                    </div>
                  )}
                </div>

                {/* Folder Selection */}
                <div className="space-y-3">
                  <Label className="text-sm font-medium">
                    Step 2: Select Folder (Required)
                  </Label>

                  {/* Breadcrumb */}
                  <div className="flex items-center gap-1 text-sm overflow-x-auto py-2 bg-muted/30 rounded px-2">
                    {folderPath.map((folder, index) => (
                      <div key={folder.id} className="flex items-center">
                        {index > 0 && (
                          <ChevronRight className="h-4 w-4 text-muted-foreground mx-1" />
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-auto py-1 px-2"
                          onClick={() => navigateBack(index)}
                        >
                          {folder.name}
                        </Button>
                      </div>
                    ))}
                  </div>

                  {/* Folder List */}
                  <div className="border rounded-lg max-h-48 overflow-y-auto">
                    {foldersLoading ? (
                      <div className="flex items-center justify-center p-8">
                        <Loader2 className="h-6 w-6 animate-spin" />
                      </div>
                    ) : foldersData?.folders.length === 0 ? (
                      <div className="p-8 text-center text-muted-foreground">
                        No folders found. Navigate into a folder or create one in Drive
                        first.
                      </div>
                    ) : (
                      foldersData?.folders.map((folder) => (
                        <div
                          key={folder.id}
                          className="flex items-center justify-between p-3 hover:bg-muted/50 border-b last:border-b-0"
                        >
                          <button
                            className="flex items-center gap-2 flex-1 text-left"
                            onClick={() => navigateToFolder(folder.id, folder.name)}
                          >
                            <Folder className="h-4 w-4 text-muted-foreground" />
                            <span>{folder.name}</span>
                          </button>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => handleSelectFolder(folder.id, folder.name)}
                          >
                            Select
                          </Button>
                        </div>
                      ))
                    )}
                  </div>

                  {/* Warning about root */}
                  {folderPath.length === 1 && (
                    <p className="text-sm text-amber-600 flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4" />
                      Navigate into a folder to select it. Drive root is not allowed.
                    </p>
                  )}
                </div>

                <DialogFooter className="gap-2">
                  <Button variant="outline" onClick={() => setShowFolderPicker(false)}>
                    Cancel
                  </Button>
                  <Button
                    onClick={() => {
                      if (folderPath.length > 1) {
                        const lastFolder = folderPath[folderPath.length - 1];
                        handleSelectFolder(lastFolder.id, lastFolder.name);
                      }
                    }}
                    disabled={configureSync.isPending || folderPath.length <= 1}
                  >
                    {configureSync.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    Use Selected Folder
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}

          {/* ADR-091: Sync Sample Preview Dialog */}
          <Dialog open={showSyncPreview} onOpenChange={setShowSyncPreview}>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Files className="h-5 w-5" />
                  Sync Sample Preview
                </DialogTitle>
                <DialogDescription>
                  Upload 3 recent files to verify your folder structure and format before syncing everything.
                </DialogDescription>
              </DialogHeader>

              {/* Preview of what will be synced */}
              <div className="space-y-3">
                {previewLoading ? (
                  <div className="flex items-center justify-center p-8">
                    <Loader2 className="h-6 w-6 animate-spin mr-2" />
                    <span>Loading preview...</span>
                  </div>
                ) : previewError ? (
                  <div className="flex items-start gap-2 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                    <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
                    <div>
                      <p className="font-medium text-red-700">Failed to load preview</p>
                      <p className="text-sm text-red-600/80">
                        {previewError instanceof Error ? previewError.message : "Unable to fetch summaries for preview"}
                      </p>
                    </div>
                  </div>
                ) : syncPreview?.total_pending === 0 ? (
                  <div className="flex items-start gap-2 p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                    <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
                    <div>
                      <p className="font-medium text-amber-700">No summaries to sync</p>
                      <p className="text-sm text-amber-600/80">
                        Generate some summaries first, then come back to sync them to Drive.
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    <Label className="text-sm font-medium">Files to sync:</Label>
                    <div className="border rounded-lg bg-muted/30 p-3 font-mono text-sm">
                      <div className="text-muted-foreground">
                        {serverConfig?.folder_name || "SummaryBot Sync"}/
                      </div>
                      <div className="ml-4">
                        <div className="text-muted-foreground">conversations/</div>
                        {syncPreview?.files?.length ? (
                          <div className="ml-4 space-y-1">
                            {syncPreview.files.map((file) => (
                              <div key={file.id} className="flex items-center gap-2">
                                <Folder className="h-3 w-3 text-muted-foreground" />
                                <span className="text-xs text-muted-foreground">
                                  {file.period_folder}/
                                </span>
                                <span className="text-primary">{file.title}.md</span>
                                <span className="text-xs text-muted-foreground">
                                  ({formatBytes(file.size_estimate)})
                                </span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="ml-4 text-muted-foreground italic">
                            (preview unavailable)
                          </div>
                        )}
                      </div>
                    </div>

                    {syncPreview?.total_pending && syncPreview.total_pending > 3 && (
                      <p className="text-sm text-muted-foreground">
                        ...and {syncPreview.total_pending - 3} more files will be synced with "Sync All"
                      </p>
                    )}

                    <div className="flex items-start gap-2 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg text-sm">
                      <HelpCircle className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" />
                      <p className="text-blue-700">
                        Sample sync creates <strong>real files</strong> in your Drive so you can verify
                        everything looks correct before syncing all {syncPreview?.total_pending || 0} files.
                      </p>
                    </div>
                  </>
                )}
              </div>

              <DialogFooter className="gap-2">
                <Button variant="outline" onClick={() => setShowSyncPreview(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={handleSampleSync}
                  disabled={sampleSync.isPending || previewLoading || !syncPreview?.total_pending}
                >
                  {sampleSync.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Files className="mr-2 h-4 w-4" />
                  )}
                  Sync 3 Sample Files
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      {/* Sync Configuration Details */}
      {syncStatus && (
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Sync Configuration
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Auto-sync on generation</p>
                <p className="font-medium">
                  {syncStatus.sync_on_generation ? "Enabled" : "Disabled"}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Sync frequency</p>
                <p className="font-medium capitalize">
                  {syncStatus.sync_frequency.replace("_", " ")}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Create server subfolders</p>
                <p className="font-medium">
                  {syncStatus.create_subfolders ? "Yes" : "No"}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Sources synced</p>
                <p className="font-medium">{syncStatus.sources_synced}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Drive Quota */}
      {driveStatus?.connected && driveStatus.quota && (
        <Card className="border-border/50">
          <CardHeader>
            <CardTitle className="text-sm font-medium">Drive Storage</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Used</span>
                <span>
                  {formatBytes(driveStatus.quota.usage)} /{" "}
                  {formatBytes(driveStatus.quota.limit)}
                </span>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary"
                  style={{
                    width: `${(driveStatus.quota.usage / driveStatus.quota.limit) * 100}%`,
                  }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}
