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
import { GuildDashboard } from "@/pages/GuildDashboard";
import { Channels } from "@/pages/Channels";
import { Summaries } from "@/pages/Summaries";
import { Schedules } from "@/pages/Schedules";
import { Webhooks } from "@/pages/Webhooks";
import { Feeds } from "@/pages/Feeds";
import { Errors } from "@/pages/Errors";
import { Settings } from "@/pages/Settings";
import NotFound from "./pages/NotFound";

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
              <Route path="schedules" element={<Schedules />} />
              <Route path="webhooks" element={<Webhooks />} />
              <Route path="feeds" element={<Feeds />} />
              <Route path="errors" element={<Errors />} />
              <Route path="settings" element={<Settings />} />
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
