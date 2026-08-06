"use client";

import React from "react";
import { Menu } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useSidebarStore } from "@/store/use-sidebar-store";
import { Breadcrumbs } from "./breadcrumbs";
import { Badge } from "@/components/ui/badge";
import { recognitionService } from "@/services/recognition";

export function Header() {
  const { toggleMobileOpen } = useSidebarStore();
  const models = useQuery({ queryKey: ["models"], queryFn: () => recognitionService.models() });

  return (
    <header className="sticky top-0 z-30 flex h-14 w-full items-center justify-between border-b border-[var(--stone-200)] bg-white/95 px-5 backdrop-blur-sm">
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

      {models.data ? (
        <Badge variant={models.data.recognition_ready ? "present" : "unknown"}>
          {models.data.recognition_ready ? "RECOGNITION READY" : "RECOGNITION NOT READY"}
        </Badge>
      ) : null}
    </header>
  );
}
