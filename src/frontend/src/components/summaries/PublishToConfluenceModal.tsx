/**
 * Publish to Confluence Modal (ADR-099)
 */

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2, FileText, AlertCircle, ExternalLink, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export interface PublishToConfluenceRequest {
  force?: boolean;
}

export interface PublishToConfluenceResult {
  success: boolean;
  page_id?: string | null;
  page_url?: string | null;
  page_version?: number | null;
  error?: string | null;
  conflict: boolean;
  previously_published: boolean;
}

interface PublishToConfluenceModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summaryTitle: string;
  isPending: boolean;
  onSubmit: (request: PublishToConfluenceRequest) => void;
  error?: string | null;
  result?: PublishToConfluenceResult | null;
}

export function PublishToConfluenceModal({
  open,
  onOpenChange,
  summaryTitle,
  isPending,
  onSubmit,
  error,
  result,
}: PublishToConfluenceModalProps) {
  const [forceUpdate, setForceUpdate] = useState(false);

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setForceUpdate(false);
    }
  }, [open]);

  const handleSubmit = () => {
    onSubmit({ force: forceUpdate });
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setForceUpdate(false);
    }
    onOpenChange(isOpen);
  };

  // Success state
  if (result?.success) {
    return (
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              Published to Confluence
            </DialogTitle>
            <DialogDescription>
              "{summaryTitle}" has been {result.previously_published ? "updated" : "published"}
            </DialogDescription>
          </DialogHeader>

          <div className="py-4 space-y-4">
            <Alert className="border-green-500/30 bg-green-500/5">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <AlertTitle>Success</AlertTitle>
              <AlertDescription>
                Page version: {result.page_version}
              </AlertDescription>
            </Alert>

            {result.page_url && (
              <a
                href={result.page_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 p-3 rounded-md border bg-muted/50 hover:bg-muted transition-colors"
              >
                <FileText className="h-4 w-4" />
                <span>View in Confluence</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>

          <DialogFooter>
            <Button onClick={() => handleOpenChange(false)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // Conflict state
  if (result?.conflict) {
    return (
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              Page Modified
            </DialogTitle>
            <DialogDescription>
              The Confluence page was edited since your last publish
            </DialogDescription>
          </DialogHeader>

          <div className="py-4 space-y-4">
            <Alert variant="destructive" className="border-amber-500/30 bg-amber-500/5">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              <AlertTitle className="text-amber-600">Version Conflict</AlertTitle>
              <AlertDescription className="text-amber-600/90">
                {result.error || "Someone edited this page in Confluence."}
                <br />
                Current version: {result.page_version}
              </AlertDescription>
            </Alert>

            <div className="flex items-start space-x-3">
              <Checkbox
                id="force-update"
                checked={forceUpdate}
                onCheckedChange={(checked) => setForceUpdate(checked as boolean)}
              />
              <div className="grid gap-1.5 leading-none">
                <label
                  htmlFor="force-update"
                  className="text-sm font-medium leading-none cursor-pointer"
                >
                  Overwrite changes
                </label>
                <p className="text-xs text-muted-foreground">
                  Replace the current page content with this summary.
                  Any manual edits will be lost.
                </p>
              </div>
            </div>

            {result.page_url && (
              <a
                href={result.page_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-primary hover:underline"
              >
                <ExternalLink className="h-3 w-3" />
                View current page in Confluence
              </a>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleSubmit}
              disabled={!forceUpdate || isPending}
            >
              {isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Updating...
                </>
              ) : (
                "Force Update"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // Default/initial state
  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Publish to Confluence
          </DialogTitle>
          <DialogDescription>
            Publish "{summaryTitle}" to your team's Confluence space
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {/* Error Alert */}
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="text-sm text-muted-foreground space-y-2">
            <p>
              This will create a new Confluence page with the summary content,
              or update the existing page if this summary was previously published.
            </p>
            <p>
              The page will include:
            </p>
            <ul className="list-disc list-inside ml-2 space-y-1">
              <li>Summary text with key points</li>
              <li>Action items as task list</li>
              <li>Participant list</li>
              <li>Source references (if available)</li>
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Publishing...
              </>
            ) : (
              <>
                <FileText className="mr-2 h-4 w-4" />
                Publish
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
