import { Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { Toaster } from "sonner";

import { TopNav } from "@/components/top-nav";
import { cn } from "@/lib/utils";

const SIDEBAR_COLLAPSED_KEY = "chatgpt2api-sidebar-collapsed";

export function AppLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  });

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  return (
    <>
      <Toaster position="top-center" richColors offset={48} />
      <main
        className="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top_left,_rgba(255,255,255,0.92),_rgba(245,239,231,0.96)_42%,_rgba(240,235,227,0.99)_100%)] text-stone-900 transition-colors duration-300 dark:bg-[radial-gradient(circle_at_top_left,_rgba(55,48,43,0.72),_rgba(28,25,23,0.98)_40%,_rgba(12,10,9,1)_100%)] dark:text-stone-100"
        style={{
          fontFamily:
            '"SF Pro Display","SF Pro Text","PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif',
        }}
      >
        <TopNav sidebarCollapsed={sidebarCollapsed} onSidebarCollapsedChange={setSidebarCollapsed} />
        <div
          className={cn(
            "box-border min-h-screen px-4 pb-2 pt-[env(safe-area-inset-top)] transition-[padding] duration-200 sm:px-6 sm:pb-4 lg:pr-8 lg:pt-4",
            sidebarCollapsed ? "lg:pl-[88px]" : "lg:pl-72",
          )}
        >
          <div className="mx-auto flex min-h-[calc(100vh-1rem)] max-w-[1440px] flex-col gap-4 sm:gap-5">
            <Outlet />
          </div>
        </div>
      </main>
    </>
  );
}
