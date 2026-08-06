"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Search, LayoutDashboard, UserPlus, Video, CalendarCheck, Users, Building2, Clock, BarChart3, Settings } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

interface SearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SEARCH_ITEMS = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Enrollment", href: "/enrollment", icon: UserPlus },
  { label: "Live Recognition", href: "/live-recognition", icon: Video },
  { label: "Attendance", href: "/attendance", icon: CalendarCheck },
  { label: "Students", href: "/students", icon: Users },
  { label: "Classrooms", href: "/classrooms", icon: Building2 },
  { label: "Sessions", href: "/sessions", icon: Clock },
  { label: "Reports", href: "/reports", icon: BarChart3 },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function SearchModal({ isOpen, onClose }: SearchModalProps) {
  const [query, setQuery] = useState("");
  const router = useRouter();

  const filtered = SEARCH_ITEMS.filter((item) =>
    item.label.toLowerCase().includes(query.toLowerCase())
  );

  const handleSelect = (href: string) => {
    router.push(href);
    onClose();
    setQuery("");
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="p-0 max-w-md overflow-hidden gap-0">
        {/* Search Input */}
        <div className="flex items-center gap-2 px-4 border-b border-[var(--stone-200)]">
          <Search className="h-4 w-4 text-[var(--ink-faint)] shrink-0" />
          <Input
            placeholder="Search pages..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="border-0 focus-visible:ring-0 shadow-none px-0 h-12 text-[13px] bg-transparent"
            autoFocus
          />
          <kbd className="shrink-0 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--ink-faint)] bg-[var(--stone-100)] rounded border border-[var(--stone-200)]">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto py-2">
          {filtered.length === 0 ? (
            <div className="p-6 text-center text-[12px] text-[var(--ink-faint)]">
              No results for &ldquo;{query}&rdquo;
            </div>
          ) : (
            <div>
              <div className="px-4 py-2 text-[9.5px] font-semibold text-[var(--ink-faint)] uppercase tracking-widest">
                Navigation
              </div>
              {filtered.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.href}
                    onClick={() => handleSelect(item.href)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-[12.5px] font-medium text-[var(--ink-muted)] hover:bg-[var(--accent-light)] hover:text-[var(--accent)] transition-colors text-left"
                  >
                    <Icon className="h-4 w-4 shrink-0 text-[var(--ink-faint)]" />
                    {item.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
