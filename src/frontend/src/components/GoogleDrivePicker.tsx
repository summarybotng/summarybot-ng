/**
 * Google Drive upload link component for importing files (ADR-082).
 *
 * Uses shared folder approach: opens a Drive folder where users can drop files.
 * Files are automatically processed by the backend scanner.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, ExternalLink, FolderUp, CheckCircle2, RefreshCw } from "lucide-react";
import { api } from "@/api/client";

interface DriveUploadInfo {
  folder_url: string;
  folder_id: string;
  instructions: string;
}

interface DriveScanResult {
  scanned: number;
  imported: number;
  errors: string[];
  message: string;
}

interface DriveUploadButtonProps {
  guildId: string;
  onUploadInitiated?: () => void;
  onImportComplete?: () => void;
}

export function DriveUploadButton({ guildId, onUploadInitiated, onImportComplete }: DriveUploadButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadInfo, setUploadInfo] = useState<DriveUploadInfo | null>(null);
  const [scanResult, setScanResult] = useState<DriveScanResult | null>(null);
  const [showDialog, setShowDialog] = useState(false);

  const handleGetUploadLink = async () => {
    setIsLoading(true);
    setError(null);
    setScanResult(null);

    try {
      const data = await api.get<DriveUploadInfo>(`/whatsapp/guilds/${guildId}/drive/upload-link`);
      setUploadInfo(data);
      setShowDialog(true);
    } catch (err) {
      const errorMessage = err instanceof Error
        ? err.message
        : (err as { detail?: { message?: string } | string })?.detail?.toString() || "Failed to get upload link";
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleOpenFolder = () => {
    if (uploadInfo?.folder_url) {
      window.open(uploadInfo.folder_url, "_blank");
      onUploadInitiated?.();
    }
  };

  const handleScanNow = async () => {
    setIsScanning(true);
    setError(null);
    setScanResult(null);

    try {
      const result = await api.post<DriveScanResult>(`/whatsapp/guilds/${guildId}/drive/scan`);
      setScanResult(result);
      if (result.imported > 0) {
        onImportComplete?.();
      }
    } catch (err) {
      const errorMessage = err instanceof Error
        ? err.message
        : (err as { detail?: { message?: string } | string })?.detail?.toString() || "Scan failed";
      setError(errorMessage);
    } finally {
      setIsScanning(false);
    }
  };

  return (
    <>
      <div className="mt-4">
        <div className="flex items-center justify-center border-t pt-4">
          <span className="text-muted-foreground text-sm px-2">or</span>
        </div>

        <Button
          variant="outline"
          className="w-full mt-4"
          onClick={handleGetUploadLink}
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Getting upload link...
            </>
          ) : (
            <>
              <svg className="h-4 w-4 mr-2" viewBox="0 0 24 24">
                <path
                  fill="currentColor"
                  d="M7.71,3.5L1.15,15L4.58,21L11.13,9.5M9.73,15L6.3,21H19.42L22.85,15M22.28,14L15.42,2H8.58L8.57,2L15.43,14"
                />
              </svg>
              Upload via Google Drive
            </>
          )}
        </Button>

        {error && (
          <Alert variant="destructive" className="mt-2">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </div>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FolderUp className="h-5 w-5" />
              Upload via Google Drive
            </DialogTitle>
            <DialogDescription>
              Drop your WhatsApp export files into the shared folder.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4 space-y-4">
            <div className="bg-muted p-4 rounded-lg">
              <h4 className="font-medium mb-2">How it works:</h4>
              <ol className="text-sm text-muted-foreground space-y-2 list-decimal list-inside">
                <li>Click "Open Upload Folder" to open Google Drive</li>
                <li>Upload your WhatsApp export (.txt or .zip)</li>
                <li>Click "Scan Now" to import immediately</li>
              </ol>
            </div>

            <div className="flex items-start gap-2 text-sm">
              <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 flex-shrink-0" />
              <span className="text-muted-foreground">
                No Google account access required - files go to a shared folder
              </span>
            </div>

            {scanResult && (
              <Alert variant={scanResult.imported > 0 ? "default" : "destructive"}>
                <AlertDescription>
                  {scanResult.message}
                  {scanResult.errors.length > 0 && (
                    <ul className="mt-2 text-sm">
                      {scanResult.errors.map((err, i) => (
                        <li key={i} className="text-red-500">{err}</li>
                      ))}
                    </ul>
                  )}
                </AlertDescription>
              </Alert>
            )}

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button variant="outline" onClick={() => setShowDialog(false)}>
              Close
            </Button>
            <Button variant="outline" onClick={handleOpenFolder}>
              <ExternalLink className="h-4 w-4 mr-2" />
              Open Upload Folder
            </Button>
            <Button onClick={handleScanNow} disabled={isScanning}>
              {isScanning ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Scanning...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Scan Now
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * Legacy export for backwards compatibility.
 * @deprecated Use DriveUploadButton instead
 */
export const DriveImportButton = DriveUploadButton;
