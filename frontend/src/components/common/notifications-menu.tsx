"use client";

import React, { useState } from "react";
import { Bell, UserCheck, AlertTriangle, Cpu } from "lucide-react";
import { NotificationItem } from "@/types";

const INITIAL_NOTIFICATIONS: NotificationItem[] = [
  {
    id: "notif_1",
    title: "Student Enrolled",
    message: "Nidhi Mahesh — 15 mask synthetic variants generated successfully.",
    time: "5 min ago",
    type: "success",
    read: false,
  },
  {
    id: "notif_2",
    title: "Unknown Face Flagged",
    message: "Unrecognized individual in CSE-101. Confidence: 41.0%.",
    time: "12 min ago",
    type: "warning",
    read: false,
  },
  {
    id: "notif_3",
    title: "Threshold Updated",
    message: "ArcFace cosine similarity cutoff set to 0.72.",
    time: "1 h ago",
    type: "info",
    read: true,
  },
];

const iconMap = {
  success: <UserCheck className="h-3.5 w-3.5 text-[var(--status-present)]" />,
  warning: <AlertTriangle className="h-3.5 w-3.5 text-[var(--status-late)]" />,
  info: <Cpu className="h-3.5 w-3.5 text-[var(--accent-muted)]" />,
  error: <AlertTriangle className="h-3.5 w-3.5 text-[var(--status-absent)]" />,
};

export function NotificationsMenu() {
  const [notifications, setNotifications] = useState(INITIAL_NOTIFICATIONS);
  const [isOpen, setIsOpen] = useState(false);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const markAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex h-8 w-8 items-center justify-center rounded-md border border-[var(--stone-200)] text-[var(--ink-faint)] hover:bg-[var(--stone-100)] hover:text-[var(--ink)] transition-colors"
        title="Notifications"
        aria-label="Notifications"
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[var(--accent)] text-[8px] font-bold text-white">
            {unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-full mt-2 z-40 w-80 rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_8px_30px_rgba(15,27,53,0.1)] overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--stone-100)]">
              <div className="flex items-center gap-2">
                <span className="text-[12.5px] font-semibold text-[var(--ink)]">Notifications</span>
                {unreadCount > 0 && (
                  <span className="text-[10px] bg-[var(--accent-light)] text-[var(--accent)] font-semibold px-1.5 py-0.5 rounded-full">
                    {unreadCount} new
                  </span>
                )}
              </div>
              <button
                onClick={markAllRead}
                className="text-[11px] text-[var(--accent)] hover:text-[var(--ink)] transition-colors font-medium"
              >
                Mark all read
              </button>
            </div>

            {/* Items */}
            <div className="divide-y divide-[var(--stone-100)] max-h-72 overflow-y-auto">
              {notifications.map((n) => (
                <div
                  key={n.id}
                  className={`px-4 py-3 flex items-start gap-3 transition-colors ${
                    n.read
                      ? "bg-white text-[var(--ink-faint)]"
                      : "bg-[var(--stone-50)] text-[var(--ink)]"
                  }`}
                >
                  <div className="mt-0.5 shrink-0 flex h-6 w-6 items-center justify-center rounded-full bg-[var(--stone-100)]">
                    {iconMap[n.type ?? "info"]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-[12px] font-semibold leading-tight">{n.title}</span>
                      <span className="text-[10px] text-[var(--ink-faint)] shrink-0 pt-0.5">{n.time}</span>
                    </div>
                    <p className="text-[11px] text-[var(--ink-faint)] leading-relaxed mt-0.5 pr-1">
                      {n.message}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
