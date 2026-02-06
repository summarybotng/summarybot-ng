import { Link, useLocation, useParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useGuild } from "@/hooks/useGuilds";
import { useUnresolvedErrorCount } from "@/hooks/useErrors";
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
  FileText,
  Calendar,
  Webhook,
  Rss,
  AlertTriangle,
  Settings,
  ChevronLeft,
} from "lucide-react";

const navItems = [
  { icon: LayoutDashboard, label: "Overview", path: "" },
  { icon: Hash, label: "Channels", path: "/channels" },
  { icon: FileText, label: "Summaries", path: "/summaries" },
  { icon: Calendar, label: "Schedules", path: "/schedules" },
  { icon: Webhook, label: "Webhooks", path: "/webhooks" },
  { icon: Rss, label: "Feeds", path: "/feeds" },
  { icon: AlertTriangle, label: "Errors", path: "/errors", showBadge: true },
  { icon: Settings, label: "Settings", path: "/settings" },
];

export function GuildSidebar() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const { data: guild } = useGuild(id || "");
  const { data: unresolvedErrorCount } = useUnresolvedErrorCount(id || "");
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
              {navItems.map(({ icon: Icon, label, path, showBadge }) => (
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
