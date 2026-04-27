/**
 * Report Issue Dialog (ADR-070)
 *
 * Two-path issue submission:
 * 1. GitHub direct - opens pre-filled GitHub issue
 * 2. Local submission - for users without GitHub
 */

import { useState, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Bug, Lightbulb, HelpCircle, Github, Mail, ExternalLink, Loader2, Check } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/authStore";

// GitHub issues URL
const GITHUB_ISSUES_URL = "https://github.com/summarybotng/summarybot-ng/issues";

type IssueType = "bug" | "feature" | "question";

interface ReportIssueDialogProps {
  open: boolean;
  onClose: () => void;
  pageUrl?: string;
  guildId?: string;
}

interface CreateIssueRequest {
  title: string;
  description: string;
  issue_type: IssueType;
  email?: string;
  page_url?: string;
  browser_info?: string;
  app_version?: string;
}

interface CreateIssueResponse {
  success: boolean;
  id: string;
  message: string;
}

// Get browser info
function getBrowserInfo(): string {
  const ua = navigator.userAgent;
  let browser = "Unknown";
  if (ua.includes("Firefox")) browser = "Firefox";
  else if (ua.includes("Chrome")) browser = "Chrome";
  else if (ua.includes("Safari")) browser = "Safari";
  else if (ua.includes("Edge")) browser = "Edge";
  return `${browser} on ${navigator.platform}`;
}

// Build GitHub issue URL with pre-filled content
function buildGitHubUrl(type: IssueType, title: string, pageUrl?: string): string {
  const templateMap: Record<IssueType, string> = {
    bug: "bug_report.md",
    feature: "feature_request.md",
    question: "question.md",
  };

  const bodyParts: string[] = [];
  if (pageUrl) bodyParts.push(`**Page:** ${pageUrl}`);
  bodyParts.push(`**Browser:** ${getBrowserInfo()}`);
  bodyParts.push("");
  bodyParts.push("---");
  bodyParts.push("");
  bodyParts.push("<!-- Describe your issue below -->");

  const params = new URLSearchParams();
  params.set("template", templateMap[type]);
  if (title) params.set("title", title);
  params.set("body", bodyParts.join("\n"));

  return `${GITHUB_ISSUES_URL}/new?${params.toString()}`;
}

export function ReportIssueDialog({ open, onClose, pageUrl, guildId }: ReportIssueDialogProps) {
  const [step, setStep] = useState<"choose" | "form" | "success">("choose");
  const [issueType, setIssueType] = useState<IssueType>("bug");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [email, setEmail] = useState("");
  const { toast } = useToast();
  const user = useAuthStore((state) => state.user);

  // Pre-fill email from user context when dialog opens (ADR-070)
  useEffect(() => {
    if (open && user?.email) {
      setEmail(user.email);
    }
  }, [open, user?.email]);

  // Submit local issue
  const submitMutation = useMutation({
    mutationFn: async (data: CreateIssueRequest) => {
      const params = guildId ? `?guild_id=${guildId}` : "";
      return api.post<CreateIssueResponse>(`/issues${params}`, data);
    },
    onSuccess: (data) => {
      setStep("success");
      toast({
        title: "Issue submitted",
        description: data.message,
      });
    },
    onError: () => {
      toast({
        title: "Failed to submit",
        description: "Please try again or use GitHub instead.",
        variant: "destructive",
      });
    },
  });

  const handleGitHubClick = () => {
    const url = buildGitHubUrl(issueType, title, pageUrl || window.location.href);
    window.open(url, "_blank");
    onClose();
  };

  const handleLocalSubmit = () => {
    const trimmedTitle = title.trim();
    const trimmedDescription = description.trim();

    // Validate minimum lengths (matches backend requirements)
    if (trimmedTitle.length < 5) {
      toast({
        title: "Title too short",
        description: "Please provide a title with at least 5 characters.",
        variant: "destructive",
      });
      return;
    }

    if (trimmedDescription.length < 10) {
      toast({
        title: "Description too short",
        description: "Please provide a description with at least 10 characters.",
        variant: "destructive",
      });
      return;
    }

    submitMutation.mutate({
      title: trimmedTitle,
      description: trimmedDescription,
      issue_type: issueType,
      email: email.trim() || undefined,
      page_url: pageUrl || window.location.href,
      browser_info: getBrowserInfo(),
    });
  };

  const handleClose = () => {
    // Reset state
    setStep("choose");
    setIssueType("bug");
    setTitle("");
    setDescription("");
    setEmail("");
    onClose();
  };

  const issueTypeOptions = [
    { value: "bug", label: "Bug Report", icon: Bug, description: "Something isn't working" },
    { value: "feature", label: "Feature Request", icon: Lightbulb, description: "Suggest an improvement" },
    { value: "question", label: "Question", icon: HelpCircle, description: "Ask for help" },
  ] as const;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {step === "success" ? "Thank you!" : "Report an Issue"}
          </DialogTitle>
          <DialogDescription>
            {step === "choose" && "How would you like to submit your feedback?"}
            {step === "form" && "Tell us what's on your mind."}
            {step === "success" && "Your feedback has been received."}
          </DialogDescription>
        </DialogHeader>

        {/* Step 1: Choose method */}
        {step === "choose" && (
          <div className="space-y-4 py-4">
            {/* Issue type selection */}
            <div className="space-y-2">
              <Label>What type of issue?</Label>
              <RadioGroup
                value={issueType}
                onValueChange={(v) => setIssueType(v as IssueType)}
                className="grid grid-cols-3 gap-2"
              >
                {issueTypeOptions.map((opt) => (
                  <Label
                    key={opt.value}
                    htmlFor={opt.value}
                    className={`flex flex-col items-center gap-1 rounded-lg border p-3 cursor-pointer hover:bg-accent ${
                      issueType === opt.value ? "border-primary bg-accent" : ""
                    }`}
                  >
                    <RadioGroupItem value={opt.value} id={opt.value} className="sr-only" />
                    <opt.icon className="h-5 w-5" />
                    <span className="text-xs font-medium">{opt.label}</span>
                  </Label>
                ))}
              </RadioGroup>
            </div>

            {/* Optional title for pre-fill */}
            <div className="space-y-2">
              <Label htmlFor="quick-title">Brief summary (optional)</Label>
              <Input
                id="quick-title"
                placeholder="e.g., Wiki page won't load"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            {/* Two paths */}
            <div className="grid gap-3 pt-2">
              <Button onClick={handleGitHubClick} className="w-full">
                <Github className="h-4 w-4 mr-2" />
                Report on GitHub
                <ExternalLink className="h-3 w-3 ml-2 opacity-50" />
              </Button>
              <Button variant="outline" onClick={() => setStep("form")} className="w-full">
                <Mail className="h-4 w-4 mr-2" />
                I don't have GitHub
              </Button>
            </div>

            <p className="text-xs text-muted-foreground text-center">
              GitHub is recommended for faster responses.
            </p>
          </div>
        )}

        {/* Step 2: Local form */}
        {step === "form" && (
          <div className="space-y-4 py-4">
            {/* Issue type (pre-selected) */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {issueType === "bug" && <Bug className="h-4 w-4" />}
              {issueType === "feature" && <Lightbulb className="h-4 w-4" />}
              {issueType === "question" && <HelpCircle className="h-4 w-4" />}
              {issueTypeOptions.find((o) => o.value === issueType)?.label}
              <Button variant="link" size="sm" className="h-auto p-0" onClick={() => setStep("choose")}>
                Change
              </Button>
            </div>

            {/* Title */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="title">Title *</Label>
                <span className={`text-xs ${title.trim().length < 5 ? "text-muted-foreground" : "text-green-600"}`}>
                  {title.trim().length}/5 min
                </span>
              </div>
              <Input
                id="title"
                placeholder="Brief summary of the issue (min 5 characters)"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
              />
            </div>

            {/* Description */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="description">Description *</Label>
                <span className={`text-xs ${description.trim().length < 10 ? "text-muted-foreground" : "text-green-600"}`}>
                  {description.trim().length}/10 min
                </span>
              </div>
              <Textarea
                id="description"
                placeholder={
                  issueType === "bug"
                    ? "What happened? What did you expect to happen? (min 10 characters)"
                    : issueType === "feature"
                    ? "Describe the feature and how it would help you. (min 10 characters)"
                    : "What would you like to know? (min 10 characters)"
                }
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={5}
                maxLength={10000}
              />
            </div>

            {/* Email (optional) */}
            <div className="space-y-2">
              <Label htmlFor="email">Email (optional)</Label>
              <Input
                id="email"
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Enter your email if you'd like updates on this issue.
              </p>
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              <Button variant="outline" onClick={() => setStep("choose")} className="flex-1">
                Back
              </Button>
              <Button
                onClick={handleLocalSubmit}
                disabled={submitMutation.isPending}
                className="flex-1"
              >
                {submitMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : null}
                Submit
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Success */}
        {step === "success" && (
          <div className="py-8 text-center space-y-4">
            <div className="mx-auto w-12 h-12 rounded-full bg-green-100 dark:bg-green-900 flex items-center justify-center">
              <Check className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <div className="space-y-2">
              <p className="font-medium">Issue submitted successfully!</p>
              <p className="text-sm text-muted-foreground">
                We appreciate your feedback and will review it soon.
              </p>
            </div>
            <Button onClick={handleClose} className="w-full">
              Done
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
