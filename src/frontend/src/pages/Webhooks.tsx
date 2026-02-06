import { useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  useWebhooks,
  useCreateWebhook,
  useUpdateWebhook,
  useDeleteWebhook,
  useTestWebhook,
} from "@/hooks/useWebhooks";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useToast } from "@/hooks/use-toast";
import { Plus, Webhook as WebhookIcon, Trash2, Loader2, Send, CheckCircle2, XCircle } from "lucide-react";
import type { Webhook } from "@/types";

export function Webhooks() {
  const { id } = useParams<{ id: string }>();
  const { data: webhooks, isLoading } = useWebhooks(id || "");
  const createWebhook = useCreateWebhook(id || "");
  const updateWebhook = useUpdateWebhook(id || "");
  const deleteWebhook = useDeleteWebhook(id || "");
  const testWebhook = useTestWebhook(id || "");
  const { toast } = useToast();

  const [createOpen, setCreateOpen] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    url: "",
    type: "generic" as Webhook["type"],
  });

  const handleCreate = async () => {
    try {
      await createWebhook.mutateAsync({
        name: formData.name,
        url: formData.url,
        type: formData.type,
        enabled: true,
      });
      setCreateOpen(false);
      setFormData({ name: "", url: "", type: "generic" });
      toast({
        title: "Webhook created",
        description: "Your new webhook has been created.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to create webhook.",
        variant: "destructive",
      });
    }
  };

  const handleToggle = async (webhookId: string, enabled: boolean) => {
    try {
      await updateWebhook.mutateAsync({
        webhookId,
        webhook: { enabled },
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to update webhook.",
        variant: "destructive",
      });
    }
  };

  const handleDelete = async (webhookId: string) => {
    try {
      await deleteWebhook.mutateAsync(webhookId);
      toast({
        title: "Webhook deleted",
        description: "The webhook has been removed.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to delete webhook.",
        variant: "destructive",
      });
    }
  };

  const handleTest = async (webhookId: string) => {
    try {
      const result = await testWebhook.mutateAsync(webhookId);
      toast({
        title: result.success ? "Test successful" : "Test failed",
        description: result.message || (result.success ? "Webhook is working correctly." : "Failed to deliver test message."),
        variant: result.success ? "default" : "destructive",
      });
    } catch (error) {
      toast({
        title: "Test failed",
        description: "Failed to test webhook.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold">Webhooks</h1>
          <p className="text-muted-foreground">
            Configure external integrations for summary delivery
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Add Webhook
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Webhook</DialogTitle>
              <DialogDescription>
                Configure a new webhook destination
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Name</label>
                <Input
                  placeholder="Slack Notifications"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">URL</label>
                <Input
                  type="url"
                  placeholder="https://hooks.slack.com/..."
                  value={formData.url}
                  onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Type</label>
                <Select
                  value={formData.type}
                  onValueChange={(v) => setFormData({ ...formData, type: v as Webhook["type"] })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="discord">Discord</SelectItem>
                    <SelectItem value="slack">Slack</SelectItem>
                    <SelectItem value="notion">Notion</SelectItem>
                    <SelectItem value="generic">Generic</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!formData.name || !formData.url || createWebhook.isPending}
              >
                {createWebhook.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="mr-2 h-4 w-4" />
                )}
                Add
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </motion.div>

      {isLoading ? (
        <WebhooksSkeleton />
      ) : webhooks?.length === 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center justify-center py-20"
        >
          <WebhookIcon className="mb-4 h-16 w-16 text-muted-foreground/30" />
          <h2 className="mb-2 text-xl font-semibold">No webhooks yet</h2>
          <p className="mb-6 text-center text-muted-foreground">
            Add a webhook to send summaries to external services
          </p>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Add Webhook
          </Button>
        </motion.div>
      ) : (
        <div className="space-y-4">
          {webhooks?.map((webhook, index) => (
            <WebhookCard
              key={webhook.id}
              webhook={webhook}
              index={index}
              onToggle={handleToggle}
              onDelete={handleDelete}
              onTest={handleTest}
              isDeleting={deleteWebhook.isPending}
              isTesting={testWebhook.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function WebhookCard({
  webhook,
  index,
  onToggle,
  onDelete,
  onTest,
  isDeleting,
  isTesting,
}: {
  webhook: Webhook;
  index: number;
  onToggle: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
  onTest: (id: string) => void;
  isDeleting: boolean;
  isTesting: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card className="border-border/50">
        <CardContent className="p-5">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="mb-2 flex items-center gap-3">
                <h3 className="font-semibold">{webhook.name}</h3>
                <Badge variant="outline" className="capitalize">
                  {webhook.type}
                </Badge>
                {webhook.last_status && (
                  <Badge
                    variant={webhook.last_status === "success" ? "default" : "destructive"}
                    className="gap-1"
                  >
                    {webhook.last_status === "success" ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      <XCircle className="h-3 w-3" />
                    )}
                    {webhook.last_status}
                  </Badge>
                )}
              </div>
              
              <p className="mb-2 text-sm text-muted-foreground">
                {webhook.url_preview}
              </p>

              {webhook.last_delivery && (
                <p className="text-sm text-muted-foreground">
                  Last delivery: {new Date(webhook.last_delivery).toLocaleString()}
                </p>
              )}
            </div>

            <div className="flex items-center gap-2">
              <Switch
                checked={webhook.enabled}
                onCheckedChange={(checked) => onToggle(webhook.id, checked)}
              />
              
              <Button
                variant="ghost"
                size="icon"
                onClick={() => onTest(webhook.id)}
                disabled={isTesting}
              >
                {isTesting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete Webhook</AlertDialogTitle>
                    <AlertDialogDescription>
                      Are you sure you want to delete "{webhook.name}"? This action cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => onDelete(webhook.id)}
                      disabled={isDeleting}
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function WebhooksSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2].map((i) => (
        <Card key={i} className="border-border/50">
          <CardContent className="p-5">
            <div className="flex justify-between">
              <div className="space-y-3">
                <div className="flex gap-2">
                  <Skeleton className="h-5 w-32" />
                  <Skeleton className="h-5 w-16" />
                </div>
                <Skeleton className="h-4 w-48" />
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-6 w-10" />
                <Skeleton className="h-8 w-8" />
                <Skeleton className="h-8 w-8" />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
