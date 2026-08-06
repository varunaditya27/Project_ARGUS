"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  UserPlus,
  Video,
  CalendarCheck,
  Users,
  Building2,
  Clock,
  BarChart3,
  FileSpreadsheet,
  Settings,
  ChevronLeft,
  ChevronRight,
  ScanFace,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useSidebarStore } from "@/store/use-sidebar-store";
import { recognitionService } from "@/services/recognition";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Enrollment", href: "/enrollment", icon: UserPlus },
  { label: "Live Recognition", href: "/live-recognition", icon: Video },
  { label: "Attendance", href: "/attendance", icon: CalendarCheck },
  { label: "Students", href: "/students", icon: Users },
  { label: "Bulk Import", href: "/import", icon: FileSpreadsheet },
  { label: "Classrooms", href: "/classrooms", icon: Building2 },
  { label: "Sessions", href: "/sessions", icon: Clock },
  { label: "Reports", href: "/reports", icon: BarChart3 },
  { label: "System", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { isCollapsed, toggleCollapse, isMobileOpen, setMobileOpen } = useSidebarStore();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => recognitionService.health(),
    refetchInterval: 30_000,
  });
  const isHealthy = health.data ? health.data.status === "ok" : health.error ? false : null;

  return (
    <>
      {/* Mobile Backdrop */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed top-0 bottom-0 left-0 z-50 flex flex-col bg-white border-r border-[var(--stone-200)] transition-all duration-200 ease-in-out select-none",
          isCollapsed ? "w-16" : "w-[220px]",
          isMobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        {/* Brand */}
        <div className={cn(
          "flex h-14 items-center border-b border-[var(--stone-200)] px-4 shrink-0",
          isCollapsed ? "justify-center" : "justify-between"
        )}>
          <Link href="/" className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--ink)] text-white shrink-0">
              <ScanFace className="h-4 w-4" />
            </div>
            {!isCollapsed && (
              <div className="flex flex-col leading-none">
                <span className="text-[13px] font-bold tracking-wide text-[var(--ink)]">ARGUS</span>
                <span className="text-[9px] text-[var(--ink-faint)] tracking-widest uppercase">Attendance System</span>
              </div>
            )}
          </Link>

          {!isCollapsed && (
            <button
              onClick={toggleCollapse}
              className="hidden lg:flex h-6 w-6 items-center justify-center rounded border border-[var(--stone-200)] text-[var(--ink-faint)] hover:bg-[var(--stone-100)] hover:text-[var(--ink)] transition-colors"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
          )}

          {isCollapsed && (
            <button
              onClick={toggleCollapse}
              className="hidden lg:flex h-6 w-6 items-center justify-center rounded border border-[var(--stone-200)] text-[var(--ink-faint)] hover:bg-[var(--stone-100)] hover:text-[var(--ink)] transition-colors mt-0"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                title={isCollapsed ? item.label : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[12.5px] transition-all duration-150 group",
                  isCollapsed ? "justify-center" : "",
                  isActive
                    ? "bg-[var(--accent-light)] text-[var(--accent)] font-semibold"
                    : "text-[var(--ink-muted)] hover:bg-[var(--stone-100)] hover:text-[var(--ink)]"
                )}
              >
                <Icon className={cn(
                  "h-4 w-4 shrink-0 transition-colors",
                  isActive ? "text-[var(--accent)]" : "text-[var(--ink-faint)] group-hover:text-[var(--ink)]"
                )} />
                {!isCollapsed && <span className="truncate">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Backend status */}
        <div className="p-3 border-t border-[var(--stone-200)] shrink-0">
          <div className={cn("flex items-center", isCollapsed ? "justify-center" : "gap-2.5")}>
            <span
              className={cn(
                "h-2 w-2 rounded-full shrink-0",
                isHealthy === null
                  ? "bg-[var(--stone-300)]"
                  : isHealthy
                    ? "bg-[var(--status-present)]"
                    : "bg-[var(--status-absent)]"
              )}
            />
            {!isCollapsed && (
              <div className="min-w-0">
                <p className="text-[11.5px] font-semibold text-[var(--ink)]">
                  {isHealthy === null ? "Contacting API" : isHealthy ? "Backend healthy" : "Backend degraded"}
                </p>
                <p className="text-[10px] text-[var(--ink-faint)] truncate">
                  {(health.data?.checks ?? []).filter((check) => !check.healthy).length || 0} checks failing
                </p>
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  );
}
