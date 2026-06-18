"use client";

import { Fragment, useEffect, useState, type ReactNode } from "react";
import { BookOpenText, Bot, Bug, FileText, Image, Images, LogOut, Menu, Palette, PanelLeftClose, PanelLeftOpen, Settings, UserPlus, type LucideIcon } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetClose, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { VersionReleaseDialog } from "@/components/version-release-dialog";
import webConfig from "@/constants/common-env";
import { fetchThirdPartyApps, type ThirdPartyAppsSettings } from "@/lib/api";
import { getValidatedAuthSession } from "@/lib/auth-session";
import { cn } from "@/lib/utils";
import { clearStoredAuthSession, type StoredAuthSession } from "@/store/auth";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const adminNavItems: NavItem[] = [
  { href: "/image", label: "生图", icon: Image },
  { href: "/accounts", label: "号池管理", icon: Bot },
  { href: "/register", label: "注册机", icon: UserPlus },
  { href: "/image-manager", label: "图片管理", icon: Images },
  { href: "/logs", label: "日志管理", icon: FileText },
  { href: "/api-docs", label: "接口文档", icon: BookOpenText },
  { href: "/debug", label: "调试", icon: Bug },
  { href: "/settings", label: "设置", icon: Settings },
];

const userNavItems: NavItem[] = [{ href: "/image", label: "画图", icon: Image }];

function buildThirdPartyHref(appUrl: string, baseUrl: string, apiKey: string) {
  const url = appUrl.trim();
  try {
    const target = new URL(url);
    target.searchParams.set("apiKey", apiKey);
    target.searchParams.set("baseUrl", baseUrl);
    return target.toString();
  } catch {
    return `${url}${url.includes("?") ? "&" : "?"}apiKey=${encodeURIComponent(apiKey)}&baseUrl=${encodeURIComponent(baseUrl)}`;
  }
}

export function TopNav({
  sidebarCollapsed,
  onSidebarCollapsedChange,
}: {
  sidebarCollapsed: boolean;
  onSidebarCollapsedChange: (collapsed: boolean) => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const pathname = location.pathname;
  const [session, setSession] = useState<StoredAuthSession | null | undefined>(undefined);
  const [thirdPartyApps, setThirdPartyApps] = useState<ThirdPartyAppsSettings | null>(null);
  const [isCanvasDialogOpen, setIsCanvasDialogOpen] = useState(false);

  useEffect(() => {
    let active = true;

    const load = async () => {
      if (pathname === "/login") {
        if (active) {
          setSession(null);
        }
        return;
      }

      const storedSession = await getValidatedAuthSession();
      if (active) {
        setSession(storedSession);
      }
    };

    void load();
    return () => {
      active = false;
    };
  }, [pathname]);

  useEffect(() => {
    if (!session) {
      setThirdPartyApps(null);
      return;
    }

    let active = true;
    const load = async () => {
      try {
        const data = await fetchThirdPartyApps();
        if (active) {
          setThirdPartyApps(data.third_party_apps);
        }
      } catch {
        if (active) {
          setThirdPartyApps(null);
        }
      }
    };
    const reload = () => void load();

    void load();
    window.addEventListener("third-party-apps-updated", reload);
    return () => {
      active = false;
      window.removeEventListener("third-party-apps-updated", reload);
    };
  }, [session]);

  const handleLogout = async () => {
    await clearStoredAuthSession();
    navigate("/login", { replace: true });
  };

  if (pathname === "/login" || session === undefined || !session) {
    return null;
  }

  const navItems = session.role === "admin" ? adminNavItems : userNavItems;
  const roleLabel = session.role === "admin" ? "管理员" : "普通用户";
  const displayName = session.name.trim() || roleLabel;
  const baseUrl = webConfig.apiUrl.replace(/\/$/, "") || window.location.origin;
  const canvas = thirdPartyApps?.infinite_canvas;
  const canvasHref = canvas?.enabled && canvas.url.trim() ? buildThirdPartyHref(canvas.url, baseUrl, session.key) : "";
  const canvasDisplayHref = canvasHref ? decodeURIComponent(canvasHref) : "";

  const handleCanvasOpen = () => {
    if (canvasHref) {
      setIsCanvasDialogOpen(true);
    }
  };

  const confirmCanvasOpen = () => {
    if (canvasHref) {
      window.open(canvasHref, "_blank", "noopener,noreferrer");
    }
    setIsCanvasDialogOpen(false);
  };

  const navigation = (
    <SidebarContent
      navItems={navItems}
      pathname={pathname}
      roleLabel={roleLabel}
      displayName={displayName}
      canvasHref={canvasHref}
      onCanvasOpen={handleCanvasOpen}
      onLogout={() => void handleLogout()}
      collapsed={sidebarCollapsed}
      closeOnSelect={false}
    />
  );

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-stone-200/70 bg-white/82 px-4 py-3 backdrop-blur-xl dark:border-white/10 dark:bg-stone-950/82 lg:hidden">
        <div className="flex items-center justify-between gap-3">
          <Sheet>
            <SheetTrigger className="inline-flex size-9 items-center justify-center rounded-md border border-stone-200 bg-white text-stone-700 transition hover:bg-stone-50 hover:text-stone-950 dark:border-white/10 dark:bg-white/5 dark:text-stone-200 dark:hover:bg-white/10">
              <Menu className="size-4" />
              <span className="sr-only">打开导航</span>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 p-0">
              <SheetHeader className="sr-only">
                <SheetTitle>ChatGPT2API 导航</SheetTitle>
              </SheetHeader>
              <SidebarContent
                navItems={navItems}
                pathname={pathname}
                roleLabel={roleLabel}
                displayName={displayName}
                canvasHref={canvasHref}
                onCanvasOpen={handleCanvasOpen}
                onLogout={() => void handleLogout()}
                closeOnSelect
              />
            </SheetContent>
          </Sheet>
          <a
            href="https://github.com/basketikun/chatgpt2api"
            target="_blank"
            rel="noreferrer"
            className="min-w-0 text-sm font-semibold text-stone-950 dark:text-stone-50"
          >
            ChatGPT2API
            <span className="ml-2 rounded-md bg-stone-100 px-1.5 py-0.5 text-[10px] font-medium text-stone-500 dark:bg-white/10 dark:text-stone-300">
              v{webConfig.appVersion}
            </span>
          </a>
          <ThemeToggle />
        </div>
      </header>

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-30 hidden border-r border-stone-200/70 bg-white/74 backdrop-blur-xl transition-[width] duration-200 dark:border-white/10 dark:bg-stone-950/72 lg:flex",
          sidebarCollapsed ? "w-[72px]" : "w-64",
        )}
      >
        {navigation}
        <button
          type="button"
          className="absolute -right-4 top-9 inline-flex size-8 items-center justify-center text-stone-500 transition hover:text-stone-950 dark:text-stone-300 dark:hover:text-white"
          onClick={() => onSidebarCollapsedChange(!sidebarCollapsed)}
          title={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
        >
          {sidebarCollapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          <span className="sr-only">{sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}</span>
        </button>
      </aside>

      <Dialog open={isCanvasDialogOpen} onOpenChange={setIsCanvasDialogOpen}>
        <DialogContent showCloseButton={false} className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>跳转到三方应用</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              该入口仅供个人测试使用，建议自行本机部署后再长期使用。跳转地址会默认带上本项目地址和当前密钥，用于自动填充连接信息；如果不放心，可以取消后手动前往应用并自行输入。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <div className="text-xs font-medium text-stone-500">完整跳转地址</div>
            <div className="max-h-28 overflow-auto break-all rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 font-mono text-xs leading-5 text-stone-700">
              {canvasDisplayHref}
            </div>
          </div>
          <DialogFooter className="pt-2">
            <DialogClose asChild>
              <Button type="button" variant="outline" className="rounded-lg border-stone-200 bg-white text-stone-700">
                取消
              </Button>
            </DialogClose>
            <Button type="button" className="rounded-lg bg-stone-950 text-white hover:bg-stone-800" onClick={confirmCanvasOpen}>
              继续跳转
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function SidebarContent({
  navItems,
  pathname,
  roleLabel,
  displayName,
  canvasHref,
  onCanvasOpen,
  onLogout,
  collapsed = false,
  closeOnSelect,
}: {
  navItems: NavItem[];
  pathname: string;
  roleLabel: string;
  displayName: string;
  canvasHref: string;
  onCanvasOpen: () => void;
  onLogout: () => void;
  collapsed?: boolean;
  closeOnSelect: boolean;
}) {
  const wrapItem = (child: ReactNode) => closeOnSelect ? <SheetClose asChild>{child}</SheetClose> : child;

  return (
    <div className={cn("flex min-h-full w-full flex-col py-4", collapsed ? "items-center px-2" : "px-3")}>
      <div className={cn("flex min-h-14 items-center", collapsed ? "w-full justify-center" : "gap-2 px-2")}>
        <a
          href="https://github.com/basketikun/chatgpt2api"
          target="_blank"
          rel="noreferrer"
          className={cn(
            "flex min-w-0 items-center rounded-lg text-stone-950 transition hover:bg-stone-100 dark:text-stone-50 dark:hover:bg-white/10",
            collapsed ? "size-8 justify-center" : "h-10 flex-1 gap-2 px-1.5",
          )}
          title="ChatGPT2API"
        >
          <img src="/github.svg" alt="" className="size-5 shrink-0 dark:invert" />
          {!collapsed ? (
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate text-[15px] font-semibold">ChatGPT2API</span>
              <span className="shrink-0 rounded-md bg-stone-100 px-1.5 py-0.5 text-[10px] font-medium text-stone-500 dark:bg-white/10 dark:text-stone-300">
                v{webConfig.appVersion}
              </span>
            </span>
          ) : null}
        </a>
      </div>

      {!collapsed ? (
        <div className="mt-4 rounded-lg border border-stone-200/80 px-3 py-2 dark:border-white/10">
          <div className="truncate text-sm font-medium text-stone-800 dark:text-stone-100">{displayName}</div>
          <div className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">{roleLabel}</div>
        </div>
      ) : null}

      <nav className={cn("flex flex-1 flex-col gap-1", collapsed ? "mt-5 w-full items-center" : "mt-5")}>
        {canvasHref ? (
          wrapItem(
            <button
              type="button"
              className={cn(
                "flex h-10 items-center rounded-lg text-left text-sm font-medium text-stone-600 transition hover:bg-stone-100 hover:text-stone-950 dark:text-stone-300 dark:hover:bg-white/10 dark:hover:text-white",
                collapsed ? "w-10 justify-center" : "w-full gap-3 px-3",
              )}
              onClick={onCanvasOpen}
              title="无限画布"
            >
              <Palette className="size-4 shrink-0" />
              {!collapsed ? "无限画布" : null}
            </button>
          )
        ) : null}
        {navItems.map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          const className = cn(
            "flex h-10 items-center rounded-lg text-sm font-medium transition",
            collapsed ? "w-10 justify-center" : "w-full gap-3 px-3",
            active
              ? "bg-stone-950 text-white dark:bg-white dark:text-stone-950"
              : "text-stone-600 hover:bg-stone-100 hover:text-stone-950 dark:text-stone-300 dark:hover:bg-white/10 dark:hover:text-white",
          );
          return (
            <Fragment key={item.href}>
              {wrapItem(
                <Link to={item.href} className={className} title={item.label}>
                  <Icon className="size-4 shrink-0" />
                  {!collapsed ? item.label : null}
                </Link>,
              )}
            </Fragment>
          );
        })}
      </nav>

      <div className={cn("mt-5 space-y-2 border-t border-stone-200/80 pt-3 dark:border-white/10", collapsed ? "w-full" : "")}>
        <div className={cn("flex items-center gap-2 rounded-lg py-1.5", collapsed ? "justify-center px-0" : "justify-between px-2")}>
          {!collapsed ? <span className="text-sm font-medium text-stone-600 dark:text-stone-300">主题</span> : null}
          <ThemeToggle />
        </div>
        <div className={cn("flex items-center gap-2 rounded-lg py-1.5", collapsed ? "justify-center px-0" : "justify-between px-2")}>
          {!collapsed ? <span className="text-sm font-medium text-stone-600 dark:text-stone-300">版本</span> : null}
          <VersionReleaseDialog />
        </div>
        <button
          type="button"
          className={cn(
            "flex h-10 w-full items-center rounded-lg text-sm font-medium text-stone-500 transition hover:bg-stone-100 hover:text-stone-950 dark:text-stone-300 dark:hover:bg-white/10 dark:hover:text-white",
            collapsed ? "justify-center px-0" : "gap-3 px-3",
          )}
          onClick={onLogout}
          title="退出登录"
        >
          <LogOut className="size-4 shrink-0" />
          {!collapsed ? "退出登录" : null}
        </button>
      </div>
    </div>
  );
}
