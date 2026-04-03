/**
 * ADR-034: Guild Prompt Templates Management Page
 *
 * Allows guild admins to create, edit, duplicate, and delete
 * reusable prompt templates for scheduled summaries.
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { formatDistanceToNow } from "date-fns";
import {
  usePromptTemplates,
  useCreatePromptTemplate,
  useUpdatePromptTemplate,
  useDeletePromptTemplate,
  useDuplicatePromptTemplate,
  usePromptTemplateUsage,
} from "@/hooks/usePromptTemplates";
import { useDefaultPrompts } from "@/hooks/usePrompts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/hooks/use-toast";
import {
  Plus,
  Loader2,
  FileText,
  MoreVertical,
  Pencil,
  Copy,
  Trash2,
  Link,
  Calendar,
} from "lucide-react";
import type { PromptTemplate } from "@/types";

interface TemplateFormData {
  name: string;
  description: string;
  content: string;
  based_on_default: string | null;
}

const initialFormData: TemplateFormData = {
  name: "",
  description: "",
  content: "",
  based_on_default: null,
};

export function PromptTemplates() {
  const { id } = useParams<{ id: string }>();
  const guildId = id || "";

  const { data: templates, isLoading } = usePromptTemplates(guildId);
  const { data: defaultPrompts } = useDefaultPrompts();
  const createTemplate = useCreatePromptTemplate(guildId);
  const updateTemplate = useUpdatePromptTemplate(guildId);
  const deleteTemplate = useDeletePromptTemplate(guildId);
  const duplicateTemplate = useDuplicatePromptTemplate(guildId);
  const { toast } = useToast();

  const [createOpen, setCreateOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<PromptTemplate | null>(null);
  const [deletingTemplate, setDeletingTemplate] = useState<PromptTemplate | null>(null);
  const [viewingUsage, setViewingUsage] = useState<PromptTemplate | null>(null);
  const [duplicatingTemplate, setDuplicatingTemplate] = useState<PromptTemplate | null>(null);
  const [duplicateName, setDuplicateName] = useState("");
  const [formData, setFormData] = useState<TemplateFormData>(initialFormData);

  const resetForm = () => {
    setFormData(initialFormData);
  };

  const openCreateDialog = (seedFromDefault?: string) => {
    const defaultPrompt = seedFromDefault
      ? defaultPrompts?.prompts.find((p) => p.name === seedFromDefault)
      : null;

    setFormData({
      name: defaultPrompt ? `Custom ${defaultPrompt.name}` : "",
      description: "",
      content: defaultPrompt?.content || "",
      based_on_default: seedFromDefault || null,
    });
    setCreateOpen(true);
  };

  const openEditDialog = (template: PromptTemplate) => {
    setFormData({
      name: template.name,
      description: template.description || "",
      content: template.content,
      based_on_default: template.based_on_default,
    });
    setEditingTemplate(template);
  };

  const handleCreate = async () => {
    if (!formData.name.trim() || !formData.content.trim()) {
      toast({
        title: "Validation Error",
        description: "Name and content are required.",
        variant: "destructive",
      });
      return;
    }

    try {
      await createTemplate.mutateAsync({
        name: formData.name.trim(),
        description: formData.description.trim() || undefined,
        content: formData.content.trim(),
        based_on_default: formData.based_on_default || undefined,
      });
      setCreateOpen(false);
      resetForm();
      toast({
        title: "Template created",
        description: "Your new prompt template has been created.",
      });
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to create template.";
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
    }
  };

  const handleUpdate = async () => {
    if (!editingTemplate || !formData.name.trim() || !formData.content.trim()) {
      toast({
        title: "Validation Error",
        description: "Name and content are required.",
        variant: "destructive",
      });
      return;
    }

    try {
      await updateTemplate.mutateAsync({
        templateId: editingTemplate.id,
        template: {
          name: formData.name.trim(),
          description: formData.description.trim() || undefined,
          content: formData.content.trim(),
        },
      });
      setEditingTemplate(null);
      resetForm();
      toast({
        title: "Template updated",
        description: "Your prompt template has been updated.",
      });
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to update template.";
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
    }
  };

  const handleDelete = async (force = false) => {
    if (!deletingTemplate) return;

    try {
      await deleteTemplate.mutateAsync({
        templateId: deletingTemplate.id,
        force,
      });
      setDeletingTemplate(null);
      toast({
        title: "Template deleted",
        description: "The prompt template has been deleted.",
      });
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to delete template.";
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
    }
  };

  const handleDuplicate = async () => {
    if (!duplicatingTemplate || !duplicateName.trim()) return;

    try {
      await duplicateTemplate.mutateAsync({
        templateId: duplicatingTemplate.id,
        newName: duplicateName.trim(),
      });
      setDuplicatingTemplate(null);
      setDuplicateName("");
      toast({
        title: "Template duplicated",
        description: "A copy of the template has been created.",
      });
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : "Failed to duplicate template.";
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
    }
  };

  if (isLoading) {
    return <TemplatesSkeleton />;
  }

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold">Prompt Templates</h1>
          <p className="text-muted-foreground">
            Create reusable prompt templates for scheduled summaries
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Template
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openCreateDialog()}>
              Start from scratch
            </DropdownMenuItem>
            {defaultPrompts?.prompts.map((prompt) => (
              <DropdownMenuItem
                key={prompt.name}
                onClick={() => openCreateDialog(prompt.name)}
              >
                Based on: {prompt.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </motion.div>

      {!templates || templates.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12">
            <FileText className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No templates yet</h3>
            <p className="text-muted-foreground text-center mb-4">
              Create custom prompt templates to use with your scheduled summaries
            </p>
            <Button onClick={() => openCreateDialog()}>
              <Plus className="mr-2 h-4 w-4" />
              Create Template
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {templates.map((template, index) => (
            <motion.div
              key={template.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <TemplateCard
                template={template}
                onEdit={() => openEditDialog(template)}
                onDuplicate={() => {
                  setDuplicatingTemplate(template);
                  setDuplicateName(`${template.name} (Copy)`);
                }}
                onDelete={() => setDeletingTemplate(template)}
                onViewUsage={() => setViewingUsage(template)}
              />
            </motion.div>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog
        open={createOpen || !!editingTemplate}
        onOpenChange={(open) => {
          if (!open) {
            setCreateOpen(false);
            setEditingTemplate(null);
            resetForm();
          }
        }}
      >
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingTemplate ? "Edit Template" : "Create Template"}
            </DialogTitle>
            <DialogDescription>
              {editingTemplate
                ? "Update your prompt template"
                : formData.based_on_default
                ? `Creating a template based on "${formData.based_on_default}"`
                : "Create a new custom prompt template"}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                placeholder="My Custom Template"
                value={formData.name}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, name: e.target.value }))
                }
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Input
                id="description"
                placeholder="A brief description of this template"
                value={formData.description}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, description: e.target.value }))
                }
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="content">Prompt Content</Label>
              <Textarea
                id="content"
                placeholder="Enter your prompt template content..."
                className="min-h-[300px] font-mono text-sm"
                value={formData.content}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, content: e.target.value }))
                }
              />
              <p className="text-xs text-muted-foreground">
                This will be used as the system prompt when generating summaries
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setCreateOpen(false);
                setEditingTemplate(null);
                resetForm();
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={editingTemplate ? handleUpdate : handleCreate}
              disabled={createTemplate.isPending || updateTemplate.isPending}
            >
              {(createTemplate.isPending || updateTemplate.isPending) && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              {editingTemplate ? "Save Changes" : "Create Template"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog
        open={!!deletingTemplate}
        onOpenChange={(open) => !open && setDeletingTemplate(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Template?</AlertDialogTitle>
            <AlertDialogDescription>
              {deletingTemplate && deletingTemplate.usage_count > 0 ? (
                <>
                  This template is used by {deletingTemplate.usage_count} schedule(s).
                  Deleting it will remove the template reference from those schedules.
                  This action cannot be undone.
                </>
              ) : (
                <>
                  Are you sure you want to delete "{deletingTemplate?.name}"?
                  This action cannot be undone.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => handleDelete(deletingTemplate?.usage_count ? true : false)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteTemplate.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Duplicate Dialog */}
      <Dialog
        open={!!duplicatingTemplate}
        onOpenChange={(open) => {
          if (!open) {
            setDuplicatingTemplate(null);
            setDuplicateName("");
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Duplicate Template</DialogTitle>
            <DialogDescription>
              Create a copy of "{duplicatingTemplate?.name}"
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="duplicate-name">New Template Name</Label>
            <Input
              id="duplicate-name"
              value={duplicateName}
              onChange={(e) => setDuplicateName(e.target.value)}
              placeholder="Enter name for the copy"
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDuplicatingTemplate(null);
                setDuplicateName("");
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleDuplicate}
              disabled={duplicateTemplate.isPending || !duplicateName.trim()}
            >
              {duplicateTemplate.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Duplicate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Usage Dialog */}
      <UsageDialog
        guildId={guildId}
        template={viewingUsage}
        onClose={() => setViewingUsage(null)}
      />
    </div>
  );
}

interface TemplateCardProps {
  template: PromptTemplate;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onViewUsage: () => void;
}

function TemplateCard({
  template,
  onEdit,
  onDuplicate,
  onDelete,
  onViewUsage,
}: TemplateCardProps) {
  return (
    <Card className="group">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <CardTitle className="text-lg">{template.name}</CardTitle>
            {template.description && (
              <CardDescription className="line-clamp-2">
                {template.description}
              </CardDescription>
            )}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onEdit}>
                <Pencil className="mr-2 h-4 w-4" />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onDuplicate}>
                <Copy className="mr-2 h-4 w-4" />
                Duplicate
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onViewUsage}>
                <Link className="mr-2 h-4 w-4" />
                View Usage
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={onDelete}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {template.based_on_default && (
            <Badge variant="secondary">
              Based on: {template.based_on_default}
            </Badge>
          )}
          {template.usage_count > 0 && (
            <Badge variant="outline">
              <Calendar className="mr-1 h-3 w-3" />
              {template.usage_count} schedule{template.usage_count !== 1 ? "s" : ""}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Updated {formatDistanceToNow(new Date(template.updated_at), { addSuffix: true })}
        </p>
      </CardContent>
    </Card>
  );
}

interface UsageDialogProps {
  guildId: string;
  template: PromptTemplate | null;
  onClose: () => void;
}

function UsageDialog({ guildId, template, onClose }: UsageDialogProps) {
  const { data: usage, isLoading } = usePromptTemplateUsage(guildId, template?.id || null);

  return (
    <Dialog open={!!template} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Template Usage</DialogTitle>
          <DialogDescription>
            Schedules using "{template?.name}"
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : usage?.schedules.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">
              This template is not used by any schedules
            </p>
          ) : (
            <ul className="space-y-2">
              {usage?.schedules.map((schedule) => (
                <li
                  key={schedule.schedule_id}
                  className="flex items-center gap-2 p-2 rounded-md bg-muted"
                >
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  {schedule.schedule_name}
                </li>
              ))}
            </ul>
          )}
        </div>
        <DialogFooter>
          <Button onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TemplatesSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-10 w-32" />
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-6 w-32" />
              <Skeleton className="h-4 w-48" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-4 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
