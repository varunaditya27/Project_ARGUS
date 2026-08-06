"use client";

import React from "react";
import { AlertTriangle } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/services/api";

/** Renders the loading, failed and empty states every data page shares. */
export function AsyncState({
  isLoading,
  error,
  isEmpty,
  emptyLabel = "Nothing here yet.",
  rows = 4,
  children,
}: {
  isLoading: boolean;
  error: unknown;
  isEmpty?: boolean;
  emptyLabel?: string;
  rows?: number;
  children: React.ReactNode;
}) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton key={index} className="h-9 w-full" />
        ))}
      </div>
    );
  }
  if (error) return <ErrorNotice error={error} />;
  if (isEmpty) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--stone-300)] px-5 py-10 text-center text-[12.5px] text-[var(--ink-faint)]">
        {emptyLabel}
      </div>
    );
  }
  return <>{children}</>;
}

/** Shows the backend's error envelope verbatim rather than a generic message. */
export function ErrorNotice({ error }: { error: unknown }) {
  const isApi = error instanceof ApiError;
  return (
    <div className="rounded-xl border border-[#D4AAAA] bg-[var(--status-absent-bg)] px-4 py-3.5 flex items-start gap-2.5">
      <AlertTriangle className="h-4 w-4 text-[var(--status-absent)] shrink-0 mt-0.5" />
      <div className="min-w-0">
        <p className="text-[12.5px] font-semibold text-[var(--status-absent)]">
          {isApi ? error.message : "Something went wrong."}
        </p>
        {isApi && (
          <p className="text-[11px] font-mono text-[var(--ink-faint)] mt-1 break-words">
            {error.code}
            {error.status ? ` · HTTP ${error.status}` : ""}
            {Object.keys(error.details).length > 0 ? ` · ${JSON.stringify(error.details)}` : ""}
          </p>
        )}
      </div>
    </div>
  );
}
