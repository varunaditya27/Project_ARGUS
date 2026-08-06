"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";

export function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  return (
    <nav className="flex items-center gap-1.5 text-[12px] text-[var(--ink-faint)] select-none" aria-label="Breadcrumb">
      <Link href="/" className="hover:text-[var(--ink)] transition-colors flex items-center" aria-label="Home">
        <Home className="h-3.5 w-3.5" />
      </Link>

      {segments.map((segment, index) => {
        const url = `/${segments.slice(0, index + 1).join("/")}`;
        const isLast = index === segments.length - 1;
        const formatted = segment.replace(/-/g, " ");

        return (
          <React.Fragment key={url}>
            <ChevronRight className="h-3 w-3 text-[var(--stone-300)]" />
            {isLast ? (
              <span className="font-medium text-[var(--ink)] capitalize">{formatted}</span>
            ) : (
              <Link href={url} className="hover:text-[var(--ink)] capitalize transition-colors">
                {formatted}
              </Link>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}
