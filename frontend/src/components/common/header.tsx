"use client";

import React from "react";
import { Menu } from "lucide-react";
import { useSidebarStore } from "@/store/use-sidebar-store";
import { Breadcrumbs } from "./breadcrumbs";
import { NotificationsMenu } from "./notifications-menu";
import { Avatar } from "@/components/ui/avatar";

export function Header() {
  const { toggleMobileOpen } = useSidebarStore();

  return (
    <header className="sticky top-0 z-30 flex h-14 w-full items-center justify-between border-b border-[var(--stone-200)] bg-white/95 px-5 backdrop-blur-sm">
      {/* Left */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleMobileOpen}
          className="flex h-7 w-7 items-center justify-center rounded border border-[var(--stone-200)] text-[var(--ink-faint)] hover:bg-[var(--stone-100)] hover:text-[var(--ink)] transition-colors lg:hidden"
          aria-label="Open menu"
        >
          <Menu className="h-4 w-4" />
        </button>
        <Breadcrumbs />
      </div>

      {/* Right */}
      <div className="flex items-center gap-3">
        <NotificationsMenu />
        <div className="w-px h-5 bg-[var(--stone-200)]" />
        <div className="flex items-center gap-2">
          <Avatar name="Nidhi Mahesh" size="sm" />
          <div className="hidden sm:flex flex-col leading-none">
            <span className="text-[12px] font-semibold text-[var(--ink)]">Nidhi Mahesh</span>
            <span className="text-[10px] text-[var(--ink-faint)]">Administrator</span>
          </div>
        </div>
      </div>
    </header>
  );
}
