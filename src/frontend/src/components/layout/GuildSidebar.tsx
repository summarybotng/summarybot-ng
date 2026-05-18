import type { ComponentType } from "react";
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
  SidebarGroupLabel,
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
  MessageSquareText,
  Boxes,
  ArrowDownToLine,
} from "lucide-react";

// ADR-040: Jobs promoted to top-level navigation
// ADR-078: Added Sources for platform-agnostic channel view
// Navigation organized into logical groups for better UX
interface NavItem {
  icon: ComponentType<{ className?: string }>;
  label: string;
  path: string;
  showBadge?: boolean;
  showJobsBadge?: boolean;
}

interface NavGroup {
  label?: string; // Optional - no label for first group
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    // Core - no label, always visible at top
    items: [
      { icon: LayoutDashboard, label: "Overview", path: "" },
      { icon: FileText, label: "Summaries", path: "/summaries" },
      { icon: Briefcase, label: "Jobs", path: "/jobs", showJobsBadge: true },
    ],
  },
  {
    label: "Sources",
    items: [
      { icon: Layers, label: "All Sources", path: "/sources" },
      { icon: Hash, label: "Channels", path: "/channels" },
      { icon: MessageSquareText, label: "WhatsApp", path: "/whatsapp" },
    ],
  },
  {
    label: "Automation",
    items: [
      { icon: Calendar, label: "Schedules", path: "/schedules" },
      { icon: Rss, label: "Feeds", path: "/feeds" },
      { icon: Webhook, label: "Webhooks", path: "/webhooks" },
    ],
  },
  {
    label: "Knowledge",
    items: [
      { icon: BookOpen, label: "Wiki", path: "/wiki" },
      { icon: Boxes, label: "RuVector Explorer", path: "/ruvector" },
      { icon: ArrowDownToLine, label: "Populate", path: "/populate" },
      { icon: BarChart3, label: "Coverage", path: "/coverage" },
    ],
  },
  {
    label: "History",
    items: [
      { icon: Archive, label: "Retrospective", path: "/archive" },
      { icon: Shield, label: "Audit Log", path: "/audit" },
    ],
  },
  {
    label: "Settings",
    items: [
      { icon: FileCode, label: "Prompts", path: "/prompt-templates" },
      { icon: AlertTriangle, label: "Errors", path: "/errors", showBadge: true },
      { icon: Settings, label: "Settings", path: "/settings" },
    ],
  },
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
        {navGroups.map((group, groupIndex) => (
          <SidebarGroup key={group.label || "core"}>
            {group.label && (
              <SidebarGroupLabel className="text-xs font-medium text-sidebar-foreground/70 uppercase tracking-wider px-2">
                {group.label}
              </SidebarGroupLabel>
            )}
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map(({ icon: Icon, label, path, showBadge, showJobsBadge }) => (
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
        ))}
      </SidebarContent>
    </Sidebar>
  );
}
