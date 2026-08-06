"use client";

import React from "react";
import { cn, getInitials } from "@/lib/utils";

interface AvatarProps {
  name: string;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function Avatar({ name, className, size = "md" }: AvatarProps) {
  const initials = getInitials(name);

  const sizeClasses = {
    sm: "h-7 w-7 text-[10px]",
    md: "h-8 w-8 text-[11px]",
    lg: "h-10 w-10 text-[13px]",
  }[size];

  return (
    <div
      className={cn(
        "rounded-full font-semibold flex items-center justify-center select-none shrink-0 bg-[var(--accent-light)] text-[var(--accent)] border border-[#C8D8F0] tracking-wide",
        sizeClasses,
        className
      )}
    >
      <span>{initials}</span>
    </div>
  );
}
