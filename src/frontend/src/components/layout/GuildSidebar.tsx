import { Link, useLocation, useParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useGuild } from "@/hooks/useGuilds";
import { useUnresolvedErrorCount } from "@/hooks/useErrors";
import { useActiveJobCount } from "@/hooks/useJobs";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  LayoutDashboard,
  Hash,
  Layers,
  FileText,
  Briefcase,
  Calendar,
  Webhook,
  Rss,
  AlertTriangle,
  Settings,
  ChevronLeft,
  Archive,
  FileCode,
  Shield,
  BookOpen,
  BarChart3,
} from "lucide-react";

// ADR-040: Jobs promoted to top-level navigation
// ADR-078: Added Sources for platform-agnostic channel view
const navItems = [
  { icon: LayoutDashboard, label: "Overview", path: "" },
  { icon: Layers, label: "Sources", path: "/sources" },
  { icon: Hash, label: "Channels", path: "/channels" },
  { icon: FileText, label: "Summaries", path: "/summaries" },
  { icon: Briefcase, label: "Jobs", path: "/jobs", showJobsBadge: true },
  { icon: Calendar, label: "Schedules", path: "/schedules" },
  { icon: FileCode, label: "Prompts", path: "/prompt-templates" },
  { icon: Webhook, label: "Webhooks", path: "/webhooks" },
  { icon: Rss, label: "Feeds", path: "/feeds" },
  { icon: AlertTriangle, label: "Errors", path: "/errors", showBadge: true },
  { icon: BookOpen, label: "Wiki", path: "/wiki" },
  { icon: BarChart3, label: "Coverage", path: "/coverage" },
  { icon: Shield, label: "Audit Log", path: "/audit" },
  { icon: Archive, label: "Retrospective", path: "/archive" },
  { icon: Settings, label: "Settings", path: "/settings" },
];

export function GuildSidebar() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const { data: guild } = useGuild(id || "");
  const { data: unresolvedErrorCount } = useUnresolvedErrorCount(id || "");
  const { data: activeJobCount } = useActiveJobCount(id || "");
  const { setOpenMobile } = useSidebar();

  const basePath = `/guilds/${id}`;

  const isActive = (path: string) => {
    const fullPath = `${basePath}${path}`;
    if (path === "") {
      return location.pathname === basePath || location.pathname === `${basePath}/`;
    }
    return location.pathname.startsWith(fullPath);
  };

  const handleNavClick = () => {
    // Close sidebar on mobile when navigating
    setOpenMobile(false);
  };

  return (
    <Sidebar className="border-r border-border">
      <SidebarHeader className="border-b border-sidebar-border p-4">
        <Link
          to="/guilds"
          onClick={handleNavClick}
          className="flex items-center gap-2 text-sm text-sidebar-foreground hover:text-sidebar-accent-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          Back to Servers
        </Link>
      </SidebarHeader>

      <SidebarHeader className="border-b border-sidebar-border p-4">
        <div className="flex items-center gap-3">
          <Avatar className="h-10 w-10">
            <AvatarImage src={guild?.icon_url || ""} alt={guild?.name} />
            <AvatarFallback className="bg-primary/20 text-primary">
              {guild?.name?.slice(0, 2).toUpperCase() || "??"}
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 truncate">
            <h2 className="truncate font-semibold text-sidebar-accent-foreground">
              {guild?.name || "Loading..."}
            </h2>
            <p className="text-xs text-sidebar-foreground">
              {guild?.member_count?.toLocaleString() || "—"} members
            </p>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map(({ icon: Icon, label, path, showBadge, showJobsBadge }) => (
                <SidebarMenuItem key={path}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive(path)}
                  >
                    <Link
                      to={`${basePath}${path}`}
                      onClick={handleNavClick}
                      className={cn(
                        "flex items-center gap-3",
                        isActive(path) && "bg-sidebar-primary text-sidebar-primary-foreground"
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      <span className="flex-1">{label}</span>
                      {/* ADR-040: Jobs badge showing active/failed count */}
                      {showJobsBadge && activeJobCount && activeJobCount.total > 0 && (
                        <Badge
                          variant={activeJobCount.hasFailedJobs ? "destructive" : "secondary"}
                          className="h-5 min-w-5 px-1.5 text-xs"
                        >
                          {activeJobCount.total > 99 ? "99+" : activeJobCount.total}
                        </Badge>
                      )}
                      {showBadge && unresolvedErrorCount && unresolvedErrorCount > 0 && (
                        <Badge variant="destructive" className="h-5 min-w-5 px-1.5 text-xs">
                          {unresolvedErrorCount > 99 ? "99+" : unresolvedErrorCount}
                        </Badge>
                      )}
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
