import { Suspense, lazy } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Header } from "@/components/layout/Header";
import { GuildLayout } from "@/components/layout/GuildLayout";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { TimezoneProvider } from "@/contexts/TimezoneContext";
import { Landing } from "@/pages/Landing";
import { Callback } from "@/pages/Callback";
import { Guilds } from "@/pages/Guilds";
import { SlackWorkspaces } from "@/pages/SlackWorkspaces";
import { GuildDashboard } from "@/pages/GuildDashboard";
import { Channels } from "@/pages/Channels";
import { Summaries } from "@/pages/Summaries";
import { Jobs } from "@/pages/Jobs";
import { Schedules } from "@/pages/Schedules";
import { Webhooks } from "@/pages/Webhooks";
import { Feeds } from "@/pages/Feeds";
import { Errors } from "@/pages/Errors";
import { Settings } from "@/pages/Settings";
import { PromptTemplates } from "@/pages/PromptTemplates";
import { AuditLog } from "@/pages/AuditLog";
import { AdminAudit } from "@/pages/AdminAudit";
import NotFound from "./pages/NotFound";
import { Skeleton } from "@/components/ui/skeleton";

// Lazy-loaded pages for code splitting
const Archive = lazy(() => import("@/pages/Archive").then(m => ({ default: m.Archive })));

// Loading fallback for lazy-loaded pages
function PageLoader() {
  return (
    <div className="space-y-6 p-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-64" />
      <div className="grid gap-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    </div>
  );
}

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TimezoneProvider>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<Landing />} />
          <Route path="/callback" element={<Callback />} />

          {/* Protected routes */}
          <Route element={<ProtectedRoute />}>
            <Route path="/guilds" element={<><Header /><Guilds /></>} />
            <Route path="/slack" element={<><Header /><SlackWorkspaces /></>} />
            <Route path="/admin/audit" element={<><Header /><AdminAudit /></>} />
            <Route
              path="/guilds/:id"
              element={
                <>
                  <Header />
                  <GuildLayout />
                </>
              }
            >
              <Route index element={<GuildDashboard />} />
              <Route path="channels" element={<Channels />} />
              <Route path="summaries" element={<Summaries />} />
              <Route path="jobs" element={<Jobs />} />
              <Route path="schedules" element={<Schedules />} />
              <Route path="webhooks" element={<Webhooks />} />
              <Route path="feeds" element={<Feeds />} />
              <Route path="errors" element={<Errors />} />
              <Route path="settings" element={<Settings />} />
              <Route path="prompt-templates" element={<PromptTemplates />} />
              <Route path="audit" element={<AuditLog />} />
              <Route path="archive" element={<Suspense fallback={<PageLoader />}><Archive /></Suspense>} />
            </Route>
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
    </TimezoneProvider>
  </QueryClientProvider>
);

export default App;
