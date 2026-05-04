/**
 * Share Target Handler Page
 *
 * Receives files shared from other apps (e.g., WhatsApp export)
 * and uploads them to the WhatsApp import API.
 */

import { Component, useEffect, useState, type ReactNode, type ErrorInfo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Loader2, CheckCircle2, AlertCircle, Upload, FileText } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/authStore";

// Error boundary to catch crashes
class ShareErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ShareReceived] Error caught by boundary:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          padding: '20px',
          backgroundColor: '#ff0000',
          color: 'white',
          fontFamily: 'monospace'
        }}>
          <h1>Share Import Crashed</h1>
          <p><strong>Error:</strong> {this.state.error?.message}</p>
          <pre style={{
            backgroundColor: '#800000',
            padding: '10px',
            overflow: 'auto',
            fontSize: '12px'
          }}>
            {this.state.error?.stack}
          </pre>
          <button
            onClick={() => window.location.href = '/'}
            style={{ marginTop: '20px', padding: '10px 20px' }}
          >
            Go to Dashboard
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

interface SharedFile {
  id: string;
  name: string;
  type: string;
  size: number;
  data: ArrayBuffer;
  timestamp: number;
}

interface Guild {
  id: string;
  name: string;
  icon?: string;
}

type UploadState = "loading" | "select-guild" | "uploading" | "success" | "error" | "no-file" | "not-authenticated";

// Wrapped export with error boundary
export default function ShareReceived() {
  return (
    <ShareErrorBoundary>
      <ShareReceivedInner />
    </ShareErrorBoundary>
  );
}

function ShareReceivedInner() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated());

  const [state, setState] = useState<UploadState>("loading");
  const [sharedFile, setSharedFile] = useState<SharedFile | null>(null);
  const [selectedGuild, setSelectedGuild] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [uploadResult, setUploadResult] = useState<{ messageCount: number; importId: string } | null>(null);

  // Fetch user's guilds
  const { data: guildsData } = useQuery({
    queryKey: ["guilds"],
    queryFn: () => api.get<{ guilds: Guild[] }>("/guilds"),
    enabled: isAuthenticated && state === "select-guild",
  });
  const guilds = guildsData?.guilds || [];

  // Check for error in URL
  useEffect(() => {
    if (searchParams.get("error")) {
      setState("error");
      setError("Failed to receive shared file");
    }
  }, [searchParams]);

  // Check authentication
  useEffect(() => {
    if (!isAuthenticated) {
      setState("not-authenticated");
    }
  }, [isAuthenticated]);

  // Load shared file from IndexedDB
  useEffect(() => {
    if (!isAuthenticated) return;

    async function loadSharedFile() {
      console.log("[ShareReceived] Starting to load shared file...");
      try {
        const db = await openDB();
        console.log("[ShareReceived] IndexedDB opened successfully");
        const tx = db.transaction("sharedFiles", "readonly");
        const store = tx.objectStore("sharedFiles");
        const request = store.get("pending");

        request.onsuccess = () => {
          const file = request.result as SharedFile | undefined;
          console.log("[ShareReceived] IndexedDB get result:", file ? `Found: ${file.name}` : "No file");
          if (file) {
            console.log("[ShareReceived] Found shared file:", file.name, "size:", file.size);
            setSharedFile(file);
            setState("select-guild");
          } else {
            console.log("[ShareReceived] No shared file found in IndexedDB");
            setState("no-file");
          }
        };

        request.onerror = () => {
          console.error("[ShareReceived] IndexedDB get error:", request.error);
          setState("error");
          setError("Failed to load shared file: " + (request.error?.message || "Unknown error"));
        };
      } catch (err) {
        console.error("[ShareReceived] Error opening IndexedDB:", err);
        setState("error");
        setError("Failed to access shared file storage: " + (err instanceof Error ? err.message : String(err)));
      }
    }

    // Small delay to ensure service worker has finished storing
    const timer = setTimeout(loadSharedFile, 500);
    return () => clearTimeout(timer);
  }, [isAuthenticated]);

  // Handle upload
  const handleUpload = async () => {
    if (!sharedFile || !selectedGuild) return;

    setState("uploading");

    try {
      // Create File object from ArrayBuffer
      const file = new File([sharedFile.data], sharedFile.name, { type: sharedFile.type });

      // Create FormData
      const formData = new FormData();
      formData.append("file", file);

      // Upload to API
      const result = await api.upload<{ import_id: string; message_count: number }>(
        `/whatsapp/guilds/${selectedGuild}/imports`,
        formData
      );

      // Clear the shared file from IndexedDB
      await clearSharedFile();

      setUploadResult({
        importId: result.import_id,
        messageCount: result.message_count,
      });
      setState("success");

    } catch (err) {
      console.error("[ShareReceived] Upload error:", err);
      setState("error");
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  };

  // Navigate to imports page
  const handleViewImport = () => {
    if (selectedGuild) {
      navigate(`/guilds/${selectedGuild}/whatsapp`);
    }
  };

  // Render based on state
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="flex items-center justify-center gap-2">
            <Upload className="h-6 w-6" />
            WhatsApp Import
          </CardTitle>
          <CardDescription>
            Import shared WhatsApp export
          </CardDescription>
        </CardHeader>
        <CardContent>
          {state === "loading" && (
            <div className="flex flex-col items-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              <p className="mt-4 text-muted-foreground">Loading shared file...</p>
            </div>
          )}

          {state === "not-authenticated" && (
            <div className="flex flex-col items-center py-8 space-y-4">
              <AlertCircle className="h-12 w-12 text-yellow-500" />
              <p className="text-center text-muted-foreground">
                Please log in to import WhatsApp chats
              </p>
              <Button onClick={() => navigate("/")}>
                Go to Login
              </Button>
            </div>
          )}

          {state === "no-file" && (
            <div className="flex flex-col items-center py-8 space-y-4">
              <FileText className="h-12 w-12 text-muted-foreground" />
              <p className="text-center text-muted-foreground">
                No file to import. Share a WhatsApp export to this app.
              </p>
              <Button variant="outline" onClick={() => navigate("/")}>
                Go to Dashboard
              </Button>
            </div>
          )}

          {state === "select-guild" && sharedFile && (
            <div className="space-y-6">
              <div className="bg-muted p-4 rounded-lg">
                <p className="font-medium">{sharedFile.name}</p>
                <p className="text-sm text-muted-foreground">
                  {(sharedFile.size / 1024).toFixed(1)} KB
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Select workspace</label>
                <Select value={selectedGuild} onValueChange={setSelectedGuild}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose a workspace..." />
                  </SelectTrigger>
                  <SelectContent>
                    {guilds.map((guild) => (
                      <SelectItem key={guild.id} value={guild.id}>
                        {guild.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <Button
                className="w-full"
                onClick={handleUpload}
                disabled={!selectedGuild}
              >
                <Upload className="h-4 w-4 mr-2" />
                Import to Workspace
              </Button>
            </div>
          )}

          {state === "uploading" && (
            <div className="flex flex-col items-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="mt-4 text-muted-foreground">Uploading and processing...</p>
            </div>
          )}

          {state === "success" && uploadResult && (
            <div className="flex flex-col items-center py-8 space-y-4">
              <CheckCircle2 className="h-12 w-12 text-green-500" />
              <div className="text-center">
                <p className="font-medium">Import successful!</p>
                <p className="text-sm text-muted-foreground">
                  {uploadResult.messageCount} messages imported
                </p>
              </div>
              <Button onClick={handleViewImport}>
                View Import
              </Button>
            </div>
          )}

          {state === "error" && (
            <div className="space-y-4">
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
              <Button variant="outline" className="w-full" onClick={() => navigate("/")}>
                Go to Dashboard
              </Button>
            </div>
          )}

        </CardContent>
      </Card>
    </div>
  );
}

// IndexedDB helper
function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("SummaryBotShare", 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains("sharedFiles")) {
        db.createObjectStore("sharedFiles", { keyPath: "id" });
      }
    };
  });
}

async function clearSharedFile(): Promise<void> {
  const db = await openDB();
  const tx = db.transaction("sharedFiles", "readwrite");
  const store = tx.objectStore("sharedFiles");
  store.delete("pending");
}
