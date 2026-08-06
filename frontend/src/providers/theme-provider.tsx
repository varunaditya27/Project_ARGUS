"use client";

import { useEffect, ReactNode } from "react";

export function ThemeProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    // Enforce light mode always
    document.documentElement.classList.remove("dark");
  }, []);

  return <>{children}</>;
}
