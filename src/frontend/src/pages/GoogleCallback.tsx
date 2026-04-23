import { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuthStore } from "@/stores/authStore";
import { Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { User, Guild } from "@/types";

export function GoogleCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = searchParams.get("token");
    const userParam = searchParams.get("user");
    const errorParam = searchParams.get("error");

    if (errorParam) {
      const errorMessages: Record<string, string> = {
        invalid_state: "Invalid OAuth state. Please try logging in again.",
        token_exchange_failed: "Failed to exchange authorization code.",
        no_id_token: "No identity token received from Google.",
        id_token_invalid: "Identity token verification failed.",
        domain_not_authorized: "Your domain is not authorized for this application.",
      };
      setError(errorMessages[errorParam] || "Authentication failed.");
      return;
    }

    if (!token || !userParam) {
      setError("Missing authentication data.");
      return;
    }

    try {
      // Parse user data from URL
      const user: User = JSON.parse(decodeURIComponent(userParam));

      // Create guild objects from guild IDs
      const guilds: Guild[] = (user.guilds || []).map((guildId: string) => ({
        id: guildId,
        name: `Guild`,
        icon: null,
        owner: false,
        permissions: "0",
      }));

      // Store auth state
      setAuth(token, user, guilds);

      // Redirect to guilds page
      navigate("/guilds");
    } catch (err) {
      console.error("Failed to parse Google auth response:", err);
      setError("Failed to process authentication response.");
    }
  }, [searchParams, navigate, setAuth]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mx-auto max-w-md text-center"
        >
          <div className="mb-6 flex justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
              <AlertCircle className="h-8 w-8 text-destructive" />
            </div>
          </div>
          <h1 className="mb-2 text-2xl font-bold">Authentication Failed</h1>
          <p className="mb-6 text-muted-foreground">{error}</p>
          <Button asChild variant="outline">
            <Link to="/">
              <RefreshCw className="mr-2 h-4 w-4" />
              Try Again
            </Link>
          </Button>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="text-center"
      >
        <Loader2 className="mx-auto mb-4 h-10 w-10 animate-spin text-primary" />
        <p className="text-lg font-medium">Completing Google authentication...</p>
        <p className="text-sm text-muted-foreground">Please wait a moment</p>
      </motion.div>
    </div>
  );
}
