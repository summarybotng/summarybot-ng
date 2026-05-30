/**
 * WhatsApp Import Management UI (ADR-081)
 *
 * Provides:
 * - Upload WhatsApp chat exports (.txt, .zip)
 * - View and manage imports
 * - View sanitized messages (pseudonyms only)
 * - Participant identity management
 * - Import deletion
 */

import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import { DriveUploadButton } from "@/components/GoogleDrivePicker";
import { useToast } from "@/hooks/use-toast";
import { format, formatDistanceToNow } from "date-fns";
import {
  Upload,
  FileText,
  Users,
  Calendar,
  MessageSquare,
  Trash2,
  Eye,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Clock,
  ChevronRight,
  Search,
  Filter,
  X,
  RefreshCw,
  Download,
  User,
  Hash,
  ArrowRight,
  Merge,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { api } from "@/api/client";

// =============================================================================
// Types
// =============================================================================

interface ImporterInfo {
  id: string;
  name: string;
  avatar?: string;
}

interface WhatsAppImport {
  id: string;
  chat_id: string;
  chat_name: string;
  imported_by: ImporterInfo;
  imported_at: string;
  original_filename: string;
  date_range: {
    start: string;
    end: string;
  };
  message_count: number;
  participant_count: number;
  status: "pending" | "processing" | "completed" | "failed";
  error_message?: string;
}

interface ImportDetail extends WhatsAppImport {
  file_size_bytes: number;
  format: string;
  processed_at?: string;
  participants: Array<{
    pseudonym: string;
    message_count: number;
  }>;
}

interface CoverageGap {
  start: string;
  end: string;
  type: "before_join" | "between_imports" | "after_last";
  days: number;
  can_fill: boolean;
  fill_hint: string;
}

interface ChatSummary {
  chat_id: string;
  chat_name: string;
  import_count: number;
  total_messages: number;
  coverage: {
    earliest: string | null;
    latest: string | null;
  };
  // ADR-112: Coverage gap awareness
  gaps?: CoverageGap[];
  detected_join_date?: string | null;
  coverage_percent?: number | null;
}

interface ListImportsResponse {
  imports: WhatsAppImport[];
  total: number;
  chats: ChatSummary[];
}

interface UploadResponse {
  import_id: string;
  status: string;
  message_count: number;
  participant_count: number;
  date_range: {
    start: string;
    end: string;
  };
  message: string;
}

interface SanitizedMessage {
  id: string;
  timestamp: string;
  sender: string;
  content: string;
  is_system: boolean;
  has_attachment: boolean;
}

interface ViewMessagesResponse {
  messages: SanitizedMessage[];
  total: number;
  page: number;
  per_page: number;
  participants: Array<{
    id: string;
    pseudonym: string;
    message_count: number;
  }>;
}

interface Participant {
  id: string;
  pseudonym: string;
  preferred_name?: string;
  message_count: number;
  alias_count: number;
}

// =============================================================================
// API Functions
// =============================================================================

async function fetchImports(guildId: string, chatId?: string): Promise<ListImportsResponse> {
  const params = chatId ? `?chat_id=${encodeURIComponent(chatId)}` : "";
  return api.get<ListImportsResponse>(`/whatsapp/guilds/${guildId}/imports${params}`);
}

async function fetchImportDetail(guildId: string, importId: string): Promise<ImportDetail> {
  return api.get<ImportDetail>(`/whatsapp/guilds/${guildId}/imports/${importId}`);
}

async function uploadImport(
  guildId: string,
  file: File,
  chatId?: string,
  chatName?: string
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (chatId) formData.append("chat_id", chatId);
  if (chatName) formData.append("chat_name", chatName);

  return api.upload<UploadResponse>(`/whatsapp/guilds/${guildId}/imports`, formData);
}

async function deleteImport(guildId: string, importId: string): Promise<void> {
  return api.delete(`/whatsapp/guilds/${guildId}/imports/${importId}`);
}

async function fetchMessages(
  guildId: string,
  importId: string,
  page: number = 1,
  search?: string
): Promise<ViewMessagesResponse> {
  const params = new URLSearchParams({ page: String(page), per_page: "50" });
  if (search) params.append("search", search);
  return api.get<ViewMessagesResponse>(
    `/whatsapp/guilds/${guildId}/imports/${importId}/messages?${params}`
  );
}

async function fetchParticipants(
  guildId: string,
  chatId: string
): Promise<{ participants: Participant[]; total: number }> {
  return api.get(`/whatsapp/guilds/${guildId}/chats/${chatId}/participants`);
}

async function mergeParticipants(
  guildId: string,
  chatId: string,
  sourceId: string,
  targetId: string
): Promise<void> {
  return api.post(`/whatsapp/guilds/${guildId}/chats/${chatId}/participants/merge`, {
    source_id: sourceId,
    target_id: targetId,
  });
}

async function updateParticipantName(
  guildId: string,
  participantId: string,
  preferredName: string | null
): Promise<void> {
  return api.patch(`/whatsapp/guilds/${guildId}/participants/${participantId}`, {
    preferred_name: preferredName,
  });
}

// =============================================================================
// Components
// =============================================================================

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function StatusBadge({ status }: { status: WhatsAppImport["status"] }) {
  const variants: Record<typeof status, { variant: "default" | "secondary" | "destructive" | "outline"; icon: React.ReactNode }> = {
    pending: { variant: "outline", icon: <Clock className="h-3 w-3" /> },
    processing: { variant: "secondary", icon: <Loader2 className="h-3 w-3 animate-spin" /> },
    completed: { variant: "default", icon: <CheckCircle2 className="h-3 w-3" /> },
    failed: { variant: "destructive", icon: <AlertCircle className="h-3 w-3" /> },
  };

  const { variant, icon } = variants[status];

  return (
    <Badge variant={variant} className="gap-1">
      {icon}
      {status}
    </Badge>
  );
}

function UploadDropzone({
  onUpload,
  isUploading,
}: {
  onUpload: (file: File) => void;
  isUploading: boolean;
}) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0) {
        onUpload(acceptedFiles[0]);
      }
    },
    [onUpload]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/plain": [".txt"],
      "application/zip": [".zip"],
    },
    maxFiles: 1,
    disabled: isUploading,
  });

  return (
    <div
      {...getRootProps()}
      className={`
        border-2 border-dashed rounded-lg p-8 text-center cursor-pointer
        transition-colors duration-200
        ${isDragActive ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-primary/50"}
        ${isUploading ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <input {...getInputProps()} />
      <Upload className="h-10 w-10 mx-auto mb-4 text-muted-foreground" />
      {isUploading ? (
        <>
          <p className="text-lg font-medium">Uploading...</p>
          <Loader2 className="h-6 w-6 animate-spin mx-auto mt-2" />
        </>
      ) : isDragActive ? (
        <p className="text-lg font-medium">Drop the file here</p>
      ) : (
        <>
          <p className="text-lg font-medium mb-1">Drop WhatsApp export here</p>
          <p className="text-sm text-muted-foreground">
            or click to browse (.txt or .zip files)
          </p>
        </>
      )}
    </div>
  );
}

function ImportCard({
  importData,
  onView,
  onDelete,
}: {
  importData: WhatsAppImport;
  onView: () => void;
  onDelete: () => void;
}) {
  const dateRange = `${format(new Date(importData.date_range.start), "MMM d")} - ${format(
    new Date(importData.date_range.end),
    "MMM d, yyyy"
  )}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-4 border rounded-lg hover:bg-muted/50 transition-colors"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <span className="font-medium truncate">{importData.original_filename}</span>
            <StatusBadge status={importData.status} />
          </div>
          <div className="text-sm text-muted-foreground space-y-1">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <MessageSquare className="h-3.5 w-3.5" />
                {importData.message_count.toLocaleString()} messages
              </span>
              <span className="flex items-center gap-1">
                <Users className="h-3.5 w-3.5" />
                {importData.participant_count} participants
              </span>
            </div>
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5" />
                {dateRange}
              </span>
              <span>
                Imported by {importData.imported_by.name}{" "}
                {formatDistanceToNow(new Date(importData.imported_at), { addSuffix: true })}
              </span>
            </div>
          </div>
          {importData.error_message && (
            <Alert variant="destructive" className="mt-2 py-2">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{importData.error_message}</AlertDescription>
            </Alert>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Button variant="ghost" size="sm" onClick={onView}>
            <Eye className="h-4 w-4 mr-1" />
            View
          </Button>
          <Button variant="ghost" size="sm" onClick={onDelete} className="text-destructive hover:text-destructive">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </motion.div>
  );
}

function ChatCard({ chat, onClick }: { chat: ChatSummary; onClick: () => void }) {
  const hasGaps = chat.gaps && chat.gaps.length > 0;
  const totalGapDays = chat.gaps?.reduce((sum, g) => sum + g.days, 0) || 0;

  return (
    <Card
      className="cursor-pointer hover:border-primary/50 transition-colors"
      onClick={onClick}
    >
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="font-medium truncate">{chat.chat_name}</h3>
              {chat.coverage_percent != null && (
                <Badge variant={chat.coverage_percent >= 80 ? "default" : "secondary"} className="text-xs">
                  {chat.coverage_percent.toFixed(0)}% coverage
                </Badge>
              )}
            </div>
            <div className="text-sm text-muted-foreground flex items-center gap-3 mt-1">
              <span>{chat.import_count} imports</span>
              <span>{chat.total_messages.toLocaleString()} messages</span>
            </div>
            {chat.coverage.earliest && chat.coverage.latest && (
              <div className="text-xs text-muted-foreground mt-1">
                Coverage: {format(new Date(chat.coverage.earliest), "MMM d, yyyy")} -{" "}
                {format(new Date(chat.coverage.latest), "MMM d, yyyy")}
              </div>
            )}
            {/* ADR-112: Show coverage gaps */}
            {hasGaps && (
              <div className="mt-2 space-y-1">
                {chat.gaps!.slice(0, 2).map((gap, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <AlertCircle className="h-3 w-3 text-amber-500 flex-shrink-0" />
                    <span className="text-amber-600 dark:text-amber-400">
                      Gap: {format(new Date(gap.start), "MMM d")} - {format(new Date(gap.end), "MMM d, yyyy")} ({gap.days} days)
                    </span>
                  </div>
                ))}
                {chat.gaps!.length > 2 && (
                  <div className="text-xs text-muted-foreground">
                    +{chat.gaps!.length - 2} more gaps ({totalGapDays} total days missing)
                  </div>
                )}
              </div>
            )}
          </div>
          <ChevronRight className="h-5 w-5 text-muted-foreground flex-shrink-0" />
        </div>
      </CardContent>
    </Card>
  );
}

function MessageList({
  guildId,
  importId,
}: {
  guildId: string;
  importId: string;
}) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["whatsapp-messages", guildId, importId, page, search],
    queryFn: () => fetchMessages(guildId, importId, page, search || undefined),
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search messages..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      <ScrollArea className="h-[400px]">
        <div className="space-y-2">
          {data?.messages.map((msg) => (
            <div
              key={msg.id}
              className={`p-3 rounded-lg ${msg.is_system ? "bg-muted/50 text-center text-sm" : "bg-card border"}`}
            >
              {!msg.is_system && (
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-sm">{msg.sender}</span>
                  <span className="text-xs text-muted-foreground">
                    {format(new Date(msg.timestamp), "MMM d, h:mm a")}
                  </span>
                  {msg.has_attachment && (
                    <Badge variant="outline" className="text-xs">
                      Attachment
                    </Badge>
                  )}
                </div>
              )}
              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
            </div>
          ))}
        </div>
      </ScrollArea>

      {data && data.total > 50 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Page {page} of {Math.ceil(data.total / 50)}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= Math.ceil(data.total / 50)}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function ParticipantList({
  guildId,
  chatId,
}: {
  guildId: string;
  chatId: string;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [mergeSource, setMergeSource] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["whatsapp-participants", guildId, chatId],
    queryFn: () => fetchParticipants(guildId, chatId),
  });

  const mergeMutation = useMutation({
    mutationFn: ({ sourceId, targetId }: { sourceId: string; targetId: string }) =>
      mergeParticipants(guildId, chatId, sourceId, targetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["whatsapp-participants", guildId, chatId] });
      setMergeSource(null);
      toast({ title: "Participants merged" });
    },
    onError: (error: Error) => {
      toast({ title: "Merge failed", description: error.message, variant: "destructive" });
    },
  });

  const updateNameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string | null }) =>
      updateParticipantName(guildId, id, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["whatsapp-participants", guildId, chatId] });
      setEditingId(null);
      toast({ title: "Name updated" });
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {mergeSource && (
        <Alert>
          <Merge className="h-4 w-4" />
          <AlertTitle>Merge mode active</AlertTitle>
          <AlertDescription>
            Click another participant to merge into the selected one, or{" "}
            <Button variant="link" className="p-0 h-auto" onClick={() => setMergeSource(null)}>
              cancel
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-2">
        {data?.participants.map((p) => (
          <div
            key={p.id}
            className={`
              p-3 border rounded-lg flex items-center justify-between
              ${mergeSource === p.id ? "border-primary bg-primary/5" : ""}
              ${mergeSource && mergeSource !== p.id ? "cursor-pointer hover:border-primary/50" : ""}
            `}
            onClick={() => {
              if (mergeSource && mergeSource !== p.id) {
                mergeMutation.mutate({ sourceId: mergeSource, targetId: p.id });
              }
            }}
          >
            <div className="flex items-center gap-3">
              <User className="h-5 w-5 text-muted-foreground" />
              <div>
                {editingId === p.id ? (
                  <div className="flex items-center gap-2">
                    <Input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      placeholder={p.pseudonym}
                      className="h-7 w-40"
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        updateNameMutation.mutate({ id: p.id, name: editName || null });
                      }}
                    >
                      <CheckCircle2 className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingId(null);
                      }}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ) : (
                  <>
                    <span className="font-medium">
                      {p.preferred_name || p.pseudonym}
                    </span>
                    {p.preferred_name && (
                      <span className="text-sm text-muted-foreground ml-2">
                        ({p.pseudonym})
                      </span>
                    )}
                  </>
                )}
                <div className="text-xs text-muted-foreground">
                  {p.message_count.toLocaleString()} messages
                  {p.alias_count > 1 && ` · ${p.alias_count} aliases`}
                </div>
              </div>
            </div>
            {!mergeSource && editingId !== p.id && (
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditingId(p.id);
                    setEditName(p.preferred_name || "");
                  }}
                >
                  Set name
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMergeSource(p.id);
                  }}
                >
                  <Merge className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function WhatsAppImports() {
  const { id: guildId } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [viewingImport, setViewingImport] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  // Fetch imports
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["whatsapp-imports", guildId, selectedChatId],
    queryFn: () => fetchImports(guildId!, selectedChatId || undefined),
    enabled: !!guildId,
  });

  // Fetch import detail
  const { data: importDetail } = useQuery({
    queryKey: ["whatsapp-import-detail", guildId, viewingImport],
    queryFn: () => fetchImportDetail(guildId!, viewingImport!),
    enabled: !!guildId && !!viewingImport,
  });

  // Upload mutation
  const handleUpload = async (file: File) => {
    if (!guildId) return;

    setIsUploading(true);
    try {
      const result = await uploadImport(guildId, file, selectedChatId || undefined);
      toast({
        title: "Import successful",
        description: result.message,
      });
      refetch();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Upload failed";
      toast({
        title: "Import failed",
        description: message,
        variant: "destructive",
      });
    } finally {
      setIsUploading(false);
    }
  };

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (importId: string) => deleteImport(guildId!, importId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["whatsapp-imports", guildId] });
      setDeleteConfirm(null);
      toast({ title: "Import deleted" });
    },
    onError: (error: Error) => {
      toast({
        title: "Delete failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">WhatsApp Imports</h1>
          <p className="text-muted-foreground">
            Upload and manage WhatsApp chat exports
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Chat selector */}
      {data?.chats && data.chats.length > 0 && (
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <Select
            value={selectedChatId || "all"}
            onValueChange={(v) => setSelectedChatId(v === "all" ? null : v)}
          >
            <SelectTrigger className="w-64">
              <SelectValue placeholder="All chats" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All chats</SelectItem>
              {data.chats.map((chat) => (
                <SelectItem key={chat.chat_id} value={chat.chat_id}>
                  {chat.chat_name} ({chat.import_count} imports)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Main content */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Upload area */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Upload Export</CardTitle>
            <CardDescription>
              Drop a WhatsApp .txt or .zip export file
            </CardDescription>
          </CardHeader>
          <CardContent>
            <UploadDropzone onUpload={handleUpload} isUploading={isUploading} />
            {/* Google Drive Import (ADR-082) */}
            {guildId && (
              <DriveUploadButton
                guildId={guildId}
                onUploadInitiated={() => {
                  toast({
                    title: "Upload folder opened",
                    description: "Drop files there then click 'Scan Now' to import",
                  });
                }}
                onImportComplete={() => {
                  refetch();
                  toast({
                    title: "Import complete",
                    description: "Files imported from Google Drive",
                  });
                }}
              />
            )}
          </CardContent>
        </Card>

        {/* Imports list */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Imports</CardTitle>
            <CardDescription>
              {data?.total || 0} imports across {data?.chats?.length || 0} chats
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!data?.imports?.length ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileText className="h-12 w-12 mx-auto mb-3 opacity-50" />
                <p>No imports yet</p>
                <p className="text-sm">Upload a WhatsApp export to get started</p>
              </div>
            ) : (
              <div className="space-y-3">
                {data.imports.map((imp) => (
                  <ImportCard
                    key={imp.id}
                    importData={imp}
                    onView={() => setViewingImport(imp.id)}
                    onDelete={() => setDeleteConfirm(imp.id)}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Chat summaries */}
      {data?.chats && data.chats.length > 0 && !selectedChatId && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Chats</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {data.chats.map((chat) => (
              <ChatCard
                key={chat.chat_id}
                chat={chat}
                onClick={() => setSelectedChatId(chat.chat_id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Import detail dialog */}
      <Dialog open={!!viewingImport} onOpenChange={() => setViewingImport(null)}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>{importDetail?.original_filename}</DialogTitle>
            <DialogDescription>
              Imported by {importDetail?.imported_by.name}{" "}
              {importDetail?.imported_at &&
                formatDistanceToNow(new Date(importDetail.imported_at), { addSuffix: true })}
            </DialogDescription>
          </DialogHeader>

          <Tabs defaultValue="messages" className="flex-1 overflow-hidden flex flex-col">
            <TabsList>
              <TabsTrigger value="messages">
                <MessageSquare className="h-4 w-4 mr-2" />
                Messages
              </TabsTrigger>
              <TabsTrigger value="participants">
                <Users className="h-4 w-4 mr-2" />
                Participants
              </TabsTrigger>
              <TabsTrigger value="details">
                <FileText className="h-4 w-4 mr-2" />
                Details
              </TabsTrigger>
            </TabsList>

            <TabsContent value="messages" className="flex-1 overflow-auto mt-4">
              {viewingImport && guildId && (
                <MessageList guildId={guildId} importId={viewingImport} />
              )}
            </TabsContent>

            <TabsContent value="participants" className="flex-1 overflow-auto mt-4">
              {importDetail && guildId && (
                <ParticipantList guildId={guildId} chatId={importDetail.chat_id} />
              )}
            </TabsContent>

            <TabsContent value="details" className="mt-4">
              {importDetail && (
                <div className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label className="text-sm font-medium">Chat</label>
                      <p className="text-sm text-muted-foreground">{importDetail.chat_name}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">Format</label>
                      <p className="text-sm text-muted-foreground">{importDetail.format}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">File Size</label>
                      <p className="text-sm text-muted-foreground">
                        {formatBytes(importDetail.file_size_bytes)}
                      </p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">Date Range</label>
                      <p className="text-sm text-muted-foreground">
                        {format(new Date(importDetail.date_range.start), "MMM d, yyyy")} -{" "}
                        {format(new Date(importDetail.date_range.end), "MMM d, yyyy")}
                      </p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">Messages</label>
                      <p className="text-sm text-muted-foreground">
                        {importDetail.message_count.toLocaleString()}
                      </p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">Participants</label>
                      <p className="text-sm text-muted-foreground">
                        {importDetail.participant_count}
                      </p>
                    </div>
                  </div>

                  {importDetail.participants.length > 0 && (
                    <div>
                      <label className="text-sm font-medium mb-2 block">
                        Participant Summary
                      </label>
                      <div className="space-y-1">
                        {importDetail.participants.map((p, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between text-sm py-1 px-2 bg-muted rounded"
                          >
                            <span>{p.pseudonym}</span>
                            <span className="text-muted-foreground">
                              {p.message_count} messages
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Import</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this import? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
