"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-[12.5px] font-medium tracking-[-0.01em] transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-40 select-none cursor-pointer",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--ink)] text-white hover:bg-[#1a2d50] border border-[var(--ink)] shadow-sm",
        primary:
          "bg-[var(--accent)] text-white hover:bg-[#1e3d8a] border border-[var(--accent)] shadow-sm",
        secondary:
          "bg-white text-[var(--ink)] border border-[var(--stone-300)] hover:bg-[var(--stone-100)] hover:border-[var(--stone-400)]",
        outline:
          "bg-transparent text-[var(--ink-muted)] border border-[var(--stone-300)] hover:bg-[var(--stone-100)] hover:text-[var(--ink)]",
        ghost:
          "bg-transparent text-[var(--ink-muted)] hover:bg-[var(--stone-100)] hover:text-[var(--ink)] border border-transparent",
        danger:
          "bg-white text-[#7A2020] border border-[#D4A0A0] hover:bg-[#FDF4F4] hover:border-[#C08080]",
      },
      size: {
        sm: "h-7 px-3 text-[11.5px]",
        default: "h-8 px-4",
        lg: "h-9 px-5 text-[13px]",
        icon: "h-7 w-7 p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  isLoading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, isLoading, children, disabled, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading ? (
          <>
            <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
            {children}
          </>
        ) : (
          children
        )}
      </button>
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
