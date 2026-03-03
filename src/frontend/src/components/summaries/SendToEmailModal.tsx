/**
 * Send to Email Modal (ADR-030)
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2, Mail, AlertCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

export interface SendToEmailRequest {
  recipients: string[];
  subject?: string;
  include_references?: boolean;
}

interface SendToEmailModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summaryTitle: string;
  isPending: boolean;
  onSubmit: (request: SendToEmailRequest) => void;
  error?: string | null;
}

// Simple email validation
function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export function SendToEmailModal({
  open,
  onOpenChange,
  summaryTitle,
  isPending,
  onSubmit,
  error,
}: SendToEmailModalProps) {
  const [emailInput, setEmailInput] = useState("");
  const [subject, setSubject] = useState("");
  const [includeReferences, setIncludeReferences] = useState(true);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Parse and validate emails
  const parseEmails = (input: string): string[] => {
    return input
      .split(/[,;\s]+/)
      .map((e) => e.trim())
      .filter((e) => e.length > 0);
  };

  const emails = parseEmails(emailInput);
  const validEmails = emails.filter(isValidEmail);
  const invalidEmails = emails.filter((e) => !isValidEmail(e));

  const handleSubmit = () => {
    if (validEmails.length === 0) {
      setValidationError("Please enter at least one valid email address.");
      return;
    }
    if (validEmails.length > 10) {
      setValidationError("Maximum 10 recipients allowed.");
      return;
    }
    setValidationError(null);

    onSubmit({
      recipients: validEmails,
      subject: subject || undefined,
      include_references: includeReferences,
    });
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      // Reset form on close
      setEmailInput("");
      setSubject("");
      setIncludeReferences(true);
      setValidationError(null);
    }
    onOpenChange(isOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            Send to Email
          </DialogTitle>
          <DialogDescription>
            Send "{summaryTitle}" to email recipients
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Error Alert */}
          {(error || validationError) && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error || validationError}</AlertDescription>
            </Alert>
          )}

          {/* Email Input */}
          <div className="space-y-2">
            <Label htmlFor="emails">Email Addresses</Label>
            <Input
              id="emails"
              placeholder="team@example.com, manager@example.com"
              value={emailInput}
              onChange={(e) => {
                setEmailInput(e.target.value);
                setValidationError(null);
              }}
            />
            <p className="text-xs text-muted-foreground">
              Separate multiple addresses with commas. Max 10 recipients.
            </p>
            {emails.length > 0 && (
              <div className="text-xs">
                <span className="text-green-600">
                  {validEmails.length} valid
                </span>
                {invalidEmails.length > 0 && (
                  <span className="text-destructive ml-2">
                    {invalidEmails.length} invalid
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Custom Subject */}
          <div className="space-y-2">
            <Label htmlFor="subject">Subject (Optional)</Label>
            <Input
              id="subject"
              placeholder="Custom email subject..."
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>

          {/* Include References */}
          <div className="flex items-center space-x-2">
            <Checkbox
              id="include-refs"
              checked={includeReferences}
              onCheckedChange={(checked) =>
                setIncludeReferences(checked as boolean)
              }
            />
            <label htmlFor="include-refs" className="text-sm cursor-pointer">
              Include source references
            </label>
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
            disabled={validEmails.length === 0 || isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Sending...
              </>
            ) : (
              <>
                <Mail className="mr-2 h-4 w-4" />
                Send Email
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
