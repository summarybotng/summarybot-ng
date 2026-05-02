import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { Loader2 } from "lucide-react";

export function ProtectedRoute() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated());
  const updateToken = useAuthStore((state) => state.updateToken);
  const [isProcessing, setIsProcessing] = useState(() => {
    // Check synchronously if we have a hash token to process
    const hash = window.location.hash;
    return hash && hash.includes("token=");
  });

  useEffect(() => {
    // ADR-079: Handle cross-subdomain token transfer via URL hash
    const hash = window.location.hash;
    if (hash && hash.includes("token=")) {
      const params = new URLSearchParams(hash.substring(1));
      const token = params.get("token");
      if (token) {
        // Store the token - user/guild info will be fetched by pages that need it
        updateToken(token);
        // Clear the hash from URL
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
      setIsProcessing(false);
    }
  }, [updateToken]);

  // Show loading while processing token from hash
  if (isProcessing) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
