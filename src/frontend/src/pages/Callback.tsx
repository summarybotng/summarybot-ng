import { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/authStore";
import { Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { User, Guild } from "@/types";

interface CallbackResponse {
  token: string;
  user: User;
  guilds: Guild[];
}

export function Callback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");

    if (!code) {
      setError("No authorization code received from Discord.");
      return;
    }

    const handleCallback = async () => {
      try {
        const response = await api.post<CallbackResponse>("/auth/callback", { code });
        setAuth(response.token, response.user, response.guilds);
        navigate("/guilds");
      } catch (err) {
        console.error("Auth callback error:", err);
        setError("Failed to complete authentication. Please try again.");
      }
    };

    handleCallback();
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
        <p className="text-lg font-medium">Completing authentication...</p>
        <p className="text-sm text-muted-foreground">Please wait a moment</p>
      </motion.div>
    </div>
  );
}
