import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, FileJson, Binary, Loader2, AlertCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { api } from "@/api/client";

interface ExportStats {
  total_units: number;
  estimated_size_bytes: number;
  estimated_size_with_embeddings_bytes: number;
  has_embeddings: boolean;
}

interface ExportDialogProps {
  guildId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const UNIT_TYPES = [
  { value: "all", label: "All Types" },
  { value: "claim", label: "Claims" },
  { value: "decision", label: "Decisions" },
  { value: "question", label: "Questions" },
  { value: "action_item", label: "Action Items" },
  { value: "context", label: "Context" },
  { value: "definition", label: "Definitions" },
  { value: "reference", label: "References" },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ExportDialog({ guildId, open, onOpenChange }: ExportDialogProps) {
  const [format, setFormat] = useState<"rvf" | "json">("rvf");
  const [includeEmbeddings, setIncludeEmbeddings] = useState(false);
  const [unitType, setUnitType] = useState("all");

  // Fetch export stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["ruvector-export-stats", guildId, unitType],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (unitType !== "all") {
        params.set("unit_types", unitType);
      }
      return api.get<ExportStats>(
        `/ruvector/guilds/${guildId}/export/stats?${params.toString()}`
      );
    },
    enabled: open,
  });

  // Export mutation
  const exportMutation = useMutation({
    mutationFn: async () => {
      const params = new URLSearchParams();
      params.set("format", format);
      params.set("include_embeddings", String(includeEmbeddings));
      if (unitType !== "all") {
        params.set("unit_types", unitType);
      }

      // Fetch as blob
      const response = await fetch(
        `/api/v1/ruvector/guilds/${guildId}/export?${params.toString()}`,
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem("token")}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error("Export failed");
      }

      // Get filename from header or generate one
      const disposition = response.headers.get("Content-Disposition");
      let filename = `knowledge_${guildId}.${format}`;
      if (disposition) {
        const match = disposition.match(/filename="(.+)"/);
        if (match) {
          filename = match[1];
        }
      }

      // Download blob
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      return { filename, size: blob.size };
    },
    onSuccess: () => {
      onOpenChange(false);
    },
  });

  const estimatedSize = includeEmbeddings
    ? stats?.estimated_size_with_embeddings_bytes
    : stats?.estimated_size_bytes;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="h-5 w-5" />
            Export Knowledge Units
          </DialogTitle>
          <DialogDescription>
            Download knowledge units as RVF (binary) or JSON file
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Stats */}
          {statsLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : stats ? (
            <div className="rounded-lg bg-muted/50 p-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Units to export:</span>
                <span className="font-medium">{stats.total_units.toLocaleString()}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Estimated size:</span>
                <span className="font-medium">{formatBytes(estimatedSize || 0)}</span>
              </div>
              {!stats.has_embeddings && includeEmbeddings && (
                <Alert variant="destructive" className="mt-2">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription className="text-xs">
                    No embeddings found in knowledge store
                  </AlertDescription>
                </Alert>
              )}
            </div>
          ) : null}

          {/* Format selection */}
          <div className="space-y-3">
            <Label>Export Format</Label>
            <RadioGroup
              value={format}
              onValueChange={(v) => setFormat(v as "rvf" | "json")}
              className="grid grid-cols-2 gap-4"
            >
              <div>
                <RadioGroupItem
                  value="rvf"
                  id="format-rvf"
                  className="peer sr-only"
                />
                <Label
                  htmlFor="format-rvf"
                  className="flex flex-col items-center justify-between rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground peer-data-[state=checked]:border-primary [&:has([data-state=checked])]:border-primary cursor-pointer"
                >
                  <Binary className="mb-2 h-6 w-6" />
                  <span className="text-sm font-medium">RVF Binary</span>
                  <span className="text-xs text-muted-foreground">Compact format</span>
                </Label>
              </div>
              <div>
                <RadioGroupItem
                  value="json"
                  id="format-json"
                  className="peer sr-only"
                />
                <Label
                  htmlFor="format-json"
                  className="flex flex-col items-center justify-between rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground peer-data-[state=checked]:border-primary [&:has([data-state=checked])]:border-primary cursor-pointer"
                >
                  <FileJson className="mb-2 h-6 w-6" />
                  <span className="text-sm font-medium">JSON</span>
                  <span className="text-xs text-muted-foreground">Human readable</span>
                </Label>
              </div>
            </RadioGroup>
          </div>

          {/* Unit type filter */}
          <div className="space-y-2">
            <Label>Unit Type</Label>
            <Select value={unitType} onValueChange={setUnitType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {UNIT_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Include embeddings toggle */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Include Embeddings</Label>
              <p className="text-xs text-muted-foreground">
                1536-dim vectors (~6KB per unit)
              </p>
            </div>
            <Switch
              checked={includeEmbeddings}
              onCheckedChange={setIncludeEmbeddings}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => exportMutation.mutate()}
            disabled={exportMutation.isPending || !stats?.total_units}
            className="gap-2"
          >
            {exportMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            Download {format.toUpperCase()}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
