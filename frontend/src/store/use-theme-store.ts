import { create } from "zustand";

interface ThemeState {
  theme: "light";
  setTheme: (theme: "light") => void;
}

export const useThemeStore = create<ThemeState>(() => ({
  theme: "light",
  setTheme: () => {
    // Light mode only — no dark mode.
    if (typeof window !== "undefined") {
      document.documentElement.classList.remove("dark");
    }
  },
}));
