import { Outlet } from "react-router-dom";
import { GuildSidebar } from "./GuildSidebar";
import { SidebarProvider, SidebarTrigger, SidebarInset } from "@/components/ui/sidebar";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";

export function GuildLayout() {
  return (
    <SidebarProvider>
      <div className="flex h-[calc(100vh-3.5rem)] w-full">
        <GuildSidebar />
        <SidebarInset className="flex-1 flex flex-col">
          {/* Mobile header with trigger */}
          <header className="flex h-12 items-center gap-2 border-b border-border px-4 md:hidden">
            <SidebarTrigger>
              <Button variant="ghost" size="icon">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle sidebar</span>
              </Button>
            </SidebarTrigger>
            <span className="text-sm font-medium">Menu</span>
          </header>
          <main className="flex-1 overflow-y-auto p-6">
            <Outlet />
          </main>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}
