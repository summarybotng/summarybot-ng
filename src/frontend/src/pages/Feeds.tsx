import { useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  useFeeds,
  useCreateFeed,
  useUpdateFeed,
  useDeleteFeed,
  useRegenerateToken,
} from "@/hooks/useFeeds";
import { useGuild } from "@/hooks/useGuilds";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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
import { useToast } from "@/hooks/use-toast";
import { Plus, Rss, Loader2, Pencil } from "lucide-react";
import { FeedCard } from "@/components/feeds/FeedCard";
import { FeedPreviewSheet } from "@/components/feeds/FeedPreviewSheet";
import {
  FeedForm,
  initialFeedFormData,
  type FeedFormData,
} from "@/components/feeds/FeedForm";
import type { Feed } from "@/types";
import { criteriaToApiBody, getDefaultCriteria } from "@/types/filters";
import type { SummaryFilterCriteria } from "@/types/filters";
import { ScrollArea } from "@/components/ui/scroll-area";

/** Convert API snake_case criteria to form camelCase criteria */
function apiCriteriaToForm(apiCriteria: Record<string, unknown> | null | undefined): SummaryFilterCriteria {
  if (!apiCriteria) return getDefaultCriteria();

  return {
    source: apiCriteria.source as SummaryFilterCriteria["source"],
    archived: apiCriteria.archived as boolean | undefined,
    createdAfter: apiCriteria.created_after as string | undefined,
    createdBefore: apiCriteria.created_before as string | undefined,
    archivePeriod: apiCriteria.archive_period as string | undefined,
    channelMode: apiCriteria.channel_mode as SummaryFilterCriteria["channelMode"],
    channelIds: apiCriteria.channel_ids as string[] | undefined,
    hasGrounding: apiCriteria.has_grounding as boolean | undefined,
    hasKeyPoints: apiCriteria.has_key_points as boolean | undefined,
    hasActionItems: apiCriteria.has_action_items as boolean | undefined,
    hasParticipants: apiCriteria.has_participants as boolean | undefined,
    minMessageCount: apiCriteria.min_message_count as number | undefined,
    maxMessageCount: apiCriteria.max_message_count as number | undefined,
    minKeyPoints: apiCriteria.min_key_points as number | undefined,
    maxKeyPoints: apiCriteria.max_key_points as number | undefined,
    minActionItems: apiCriteria.min_action_items as number | undefined,
    maxActionItems: apiCriteria.max_action_items as number | undefined,
    minParticipants: apiCriteria.min_participants as number | undefined,
    maxParticipants: apiCriteria.max_participants as number | undefined,
    platform: apiCriteria.platform as string | undefined,
    summaryLength: apiCriteria.summary_length as string | undefined,
    perspective: apiCriteria.perspective as string | undefined,
  };
}

export function Feeds() {
  const { id } = useParams<{ id: string }>();
  const { data: feeds, isLoading } = useFeeds(id || "");
  const { data: guild } = useGuild(id || "");
  const createFeed = useCreateFeed(id || "");
  const updateFeed = useUpdateFeed(id || "");
  const deleteFeed = useDeleteFeed(id || "");
  const regenerateToken = useRegenerateToken(id || "");
  const { toast } = useToast();

  const [createOpen, setCreateOpen] = useState(false);
  const [editingFeed, setEditingFeed] = useState<Feed | null>(null);
  const [previewFeed, setPreviewFeed] = useState<Feed | null>(null);
  const [formData, setFormData] = useState<FeedFormData>(initialFeedFormData);

  const resetForm = () => {
    setFormData(initialFeedFormData);
  };

  const openEditDialog = (feed: Feed) => {
    setFormData({
      channel_id: feed.channel_id,
      feed_type: feed.feed_type,
      is_public: feed.is_public,
      title: feed.title || "",
      description: feed.description || "",
      max_items: feed.max_items || 50,
      include_full_content: feed.include_full_content ?? true,
      // ADR-037: Include filter criteria (convert from API snake_case to form camelCase)
      criteria: apiCriteriaToForm(feed.criteria as Record<string, unknown> | null),
    });
    setEditingFeed(feed);
  };

  const handleCreate = async () => {
    try {
      const newFeed = await createFeed.mutateAsync({
        channel_id: formData.channel_id,
        feed_type: formData.feed_type,
        is_public: formData.is_public,
        title: formData.title || undefined,
        description: formData.description || undefined,
        max_items: formData.max_items,
        include_full_content: formData.include_full_content,
        // ADR-037: Include filter criteria (convert to snake_case for API)
        criteria: criteriaToApiBody(formData.criteria) as any,
      });
      setCreateOpen(false);
      resetForm();

      // Copy URL to clipboard
      await navigator.clipboard.writeText(newFeed.url);
      toast({
        title: "Feed created",
        description: "Feed URL has been copied to your clipboard.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to create feed.",
        variant: "destructive",
      });
    }
  };

  const handleEdit = async () => {
    if (!editingFeed) return;

    try {
      await updateFeed.mutateAsync({
        feedId: editingFeed.id,
        feed: {
          title: formData.title || undefined,
          description: formData.description || undefined,
          is_public: formData.is_public,
          max_items: formData.max_items,
          include_full_content: formData.include_full_content,
          // ADR-037: Include filter criteria (convert to snake_case for API)
          criteria: criteriaToApiBody(formData.criteria) as any,
        },
      });
      setEditingFeed(null);
      resetForm();
      toast({
        title: "Feed updated",
        description: "Your feed has been updated.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to update feed.",
        variant: "destructive",
      });
    }
  };

  const handleDelete = async (feedId: string) => {
    try {
      await deleteFeed.mutateAsync(feedId);
      toast({
        title: "Feed deleted",
        description: "The feed has been removed.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to delete feed.",
        variant: "destructive",
      });
    }
  };

  const handleRegenerateToken = async (feedId: string) => {
    try {
      const result = await regenerateToken.mutateAsync(feedId);
      await navigator.clipboard.writeText(result.url);
      toast({
        title: "Token regenerated",
        description: "New feed URL has been copied to your clipboard.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to regenerate token.",
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
          <h1 className="text-2xl font-bold">Feeds</h1>
          <p className="text-muted-foreground">
            Create RSS or Atom feeds for your summaries
          </p>
        </div>

        {/* Create Dialog */}
        <Dialog
          open={createOpen}
          onOpenChange={(open) => {
            setCreateOpen(open);
            if (!open) resetForm();
          }}
        >
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Create Feed
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
            <DialogHeader>
              <DialogTitle>Create Feed</DialogTitle>
              <DialogDescription>
                Create an RSS or Atom feed for your summaries
              </DialogDescription>
            </DialogHeader>
            <ScrollArea className="flex-1 max-h-[60vh] pr-4">
              <FeedForm
                formData={formData}
                onChange={setFormData}
                channels={guild?.channels || []}
                guildId={id}
              />
            </ScrollArea>
            <DialogFooter className="pt-4 border-t">
              <Button variant="outline" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreate} disabled={createFeed.isPending}>
                {createFeed.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="mr-2 h-4 w-4" />
                )}
                Create
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </motion.div>

      {/* Edit Dialog */}
      <Dialog
        open={!!editingFeed}
        onOpenChange={(open) => {
          if (!open) {
            setEditingFeed(null);
            resetForm();
          }
        }}
      >
        <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Edit Feed</DialogTitle>
            <DialogDescription>
              Update your feed settings
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="flex-1 max-h-[60vh] pr-4">
            <FeedForm
              formData={formData}
              onChange={setFormData}
              channels={guild?.channels || []}
              guildId={id}
              isEdit
            />
          </ScrollArea>
          <DialogFooter className="pt-4 border-t">
            <Button variant="outline" onClick={() => setEditingFeed(null)}>
              Cancel
            </Button>
            <Button onClick={handleEdit} disabled={updateFeed.isPending}>
              {updateFeed.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Pencil className="mr-2 h-4 w-4" />
              )}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {isLoading ? (
        <FeedsSkeleton />
      ) : feeds?.length === 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center justify-center py-20"
        >
          <Rss className="mb-4 h-16 w-16 text-muted-foreground/30" />
          <h2 className="mb-2 text-xl font-semibold">No feeds yet</h2>
          <p className="mb-6 max-w-md text-center text-muted-foreground">
            Create an RSS or Atom feed to subscribe to summaries in your favorite
            feed reader.
          </p>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Create Feed
          </Button>
        </motion.div>
      ) : (
        <div className="space-y-4">
          {feeds?.map((feed, index) => (
            <FeedCard
              key={feed.id}
              feed={feed}
              index={index}
              onEdit={openEditDialog}
              onDelete={handleDelete}
              onRegenerateToken={handleRegenerateToken}
              onPreview={setPreviewFeed}
              isDeleting={deleteFeed.isPending}
              isRegenerating={regenerateToken.isPending}
            />
          ))}
        </div>
      )}

      {/* Feed Preview Sheet */}
      <FeedPreviewSheet
        feed={previewFeed}
        guildId={id || ""}
        open={!!previewFeed}
        onOpenChange={(open) => {
          if (!open) setPreviewFeed(null);
        }}
      />
    </div>
  );
}

function FeedsSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <Card key={i} className="border-border/50">
          <CardContent className="p-5">
            <div className="flex justify-between">
              <div className="space-y-3">
                <div className="flex gap-2">
                  <Skeleton className="h-5 w-40" />
                  <Skeleton className="h-5 w-12" />
                  <Skeleton className="h-5 w-16" />
                </div>
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-4 w-48" />
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-8 w-8" />
                <Skeleton className="h-8 w-8" />
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
