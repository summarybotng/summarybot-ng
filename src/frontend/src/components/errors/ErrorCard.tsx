import { motion } from "framer-motion";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { parseAsUTC } from "@/contexts/TimezoneContext";
import { Badge } from "@/components/ui/badge";
import {
  AlertCircle,
  AlertTriangle,
  Info,
  XCircle,
  CheckCircle,
  Hash,
} from "lucide-react";
import type { ErrorLogItem, ErrorSeverity, ErrorType } from "@/types/errors";

interface ErrorCardProps {
  error: ErrorLogItem;
  index: number;
  onClick: () => void;
}

const severityConfig: Record<
  ErrorSeverity,
  { icon: typeof AlertCircle; color: string; bg: string; label: string }
> = {
  critical: {
    icon: XCircle,
    color: "text-red-500",
    bg: "bg-red-500/10 border-red-500/20",
    label: "Critical",
  },
  error: {
    icon: AlertCircle,
    color: "text-orange-500",
    bg: "bg-orange-500/10 border-orange-500/20",
    label: "Error",
  },
  warning: {
    icon: AlertTriangle,
    color: "text-yellow-500",
    bg: "bg-yellow-500/10 border-yellow-500/20",
    label: "Warning",
  },
  info: {
    icon: Info,
    color: "text-blue-500",
    bg: "bg-blue-500/10 border-blue-500/20",
    label: "Info",
  },
};

const errorTypeLabels: Record<ErrorType, string> = {
  discord_permission: "Permission",
  discord_not_found: "Not Found",
  discord_rate_limit: "Rate Limit",
  api_error: "API Error",
  database_error: "Database",
  summarization_error: "Summarization",
  schedule_error: "Schedule",
  webhook_error: "Webhook",
  unknown: "Unknown",
};

export function ErrorCard({ error, index, onClick }: ErrorCardProps) {
  const severity = severityConfig[error.severity];
  const SeverityIcon = severity.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      onClick={onClick}
      className={cn(
        "flex items-center gap-4 rounded-lg border p-4 cursor-pointer transition-all hover:bg-muted/50",
        severity.bg,
        error.is_resolved && "opacity-60"
      )}
    >
      <div className={cn("flex-shrink-0", severity.color)}>
        <SeverityIcon className="h-5 w-5" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <Badge variant="outline" className="text-xs">
            {errorTypeLabels[error.error_type]}
          </Badge>
          {error.is_resolved && (
            <Badge variant="secondary" className="text-xs gap-1">
              <CheckCircle className="h-3 w-3" />
              Resolved
            </Badge>
          )}
        </div>
        <p className="text-sm font-medium truncate">{error.message}</p>
        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
          {error.channel_name && (
            <span className="flex items-center gap-1">
              <Hash className="h-3 w-3" />
              {error.channel_name}
            </span>
          )}
          <span>{error.operation}</span>
        </div>
      </div>

      <div className="flex-shrink-0 text-xs text-muted-foreground">
        {formatDistanceToNow(parseAsUTC(error.created_at), { addSuffix: true })}
      </div>
    </motion.div>
  );
}
