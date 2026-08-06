"use client";

import React from "react";
import { QueryProvider } from "@/providers/query-provider";
import { ThemeProvider } from "@/providers/theme-provider";
import { Sidebar } from "@/components/common/sidebar";
import { Header } from "@/components/common/header";
import { useSidebarStore } from "@/store/use-sidebar-store";
import { cn } from "@/lib/utils";

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { isCollapsed } = useSidebarStore();

  return (
    <QueryProvider>
      <ThemeProvider>
        <div className="min-h-screen bg-[var(--stone-50)] text-[var(--ink)] flex flex-col transition-colors">
          <Sidebar />

          <div
            className={cn(
              "flex flex-col min-h-screen transition-all duration-200 ease-in-out",
              isCollapsed ? "lg:pl-16" : "lg:pl-[220px]"
            )}
          >
            <Header />
            <main className="flex-1 px-6 py-6 max-w-7xl w-full mx-auto">
              {children}
            </main>
            <footer className="py-3 px-6 border-t border-[var(--stone-200)]">
              <p className="text-[11px] text-[var(--ink-faint)] tracking-wide text-center">
                ARGUS Attendance Recognition System &nbsp;·&nbsp; Academic Administration
              </p>
            </footer>
          </div>
        </div>
      </ThemeProvider>
    </QueryProvider>
  );
}
