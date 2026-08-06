"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded px-2 py-0.5 text-[10.5px] font-medium tracking-wide border select-none",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--stone-100)] text-[var(--ink-muted)] border-[var(--stone-300)]",
        secondary:
          "bg-transparent text-[var(--ink-faint)] border-[var(--stone-200)]",
        outline:
          "bg-transparent text-[var(--ink-muted)] border-[var(--stone-300)]",
        present:
          "bg-[var(--status-present-bg)] text-[var(--status-present)] border-[#A8D8BC]",
        absent:
          "bg-[var(--status-absent-bg)] text-[var(--status-absent)] border-[#D4AAAA] line-through",
        late:
          "bg-[var(--status-late-bg)] text-[var(--status-late)] border-[#DDCBA0]",
        unknown:
          "bg-[var(--status-unknown-bg)] text-[var(--status-unknown)] border-[var(--stone-300)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
