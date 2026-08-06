"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-8 w-full rounded-md border border-[var(--stone-300)] bg-white px-3 py-1.5 text-[12.5px] text-[var(--ink)] placeholder:text-[var(--ink-faint)] transition-colors focus-visible:outline-none focus-visible:border-[var(--accent)] focus-visible:ring-2 focus-visible:ring-[var(--accent-light)] disabled:cursor-not-allowed disabled:opacity-50 shadow-[0_1px_2px_rgba(15,27,53,0.04)]",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
