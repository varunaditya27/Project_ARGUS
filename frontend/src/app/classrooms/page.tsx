"use client";

import React, { useState } from "react";
import { Camera, Users, Wifi, WifiOff, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { MOCK_CLASSROOMS } from "@/mock/classroom-mock";
import { Classroom } from "@/types";

const statusConfig: Record<Classroom["status"], { badge: "present" | "unknown" | "late"; icon: React.ReactNode; label: string }> = {
  ONLINE: {
    badge: "present",
    icon: <Wifi className="h-3.5 w-3.5 text-[var(--status-present)]" />,
    label: "Online",
  },
  OFFLINE: {
    badge: "unknown",
    icon: <WifiOff className="h-3.5 w-3.5 text-[var(--ink-faint)]" />,
    label: "Offline",
  },
  MAINTENANCE: {
    badge: "late",
    icon: <Wrench className="h-3.5 w-3.5 text-[var(--status-late)]" />,
    label: "Maintenance",
  },
};

export default function ClassroomsPage() {
  const [classrooms] = useState(MOCK_CLASSROOMS);

  return (
    <div className="space-y-7">
      {/* Page Header */}
      <div>
        <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Classrooms</h1>
        <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
          {classrooms.filter((r) => r.status === "ONLINE").length} of {classrooms.length} rooms online
        </p>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {classrooms.map((room) => {
          const cfg = statusConfig[room.status];
          return (
            <div
              key={room.id}
              className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)] overflow-hidden"
            >
              {/* Card Header */}
              <div className="px-4 py-3 border-b border-[var(--stone-100)] flex items-center justify-between">
                <div>
                  <p className="text-[13.5px] font-semibold text-[var(--ink)]">{room.name}</p>
                  <p className="text-[10.5px] font-mono text-[var(--ink-faint)] mt-0.5">{room.code}</p>
                </div>
                <Badge variant={cfg.badge}>{cfg.label}</Badge>
              </div>

              {/* Card Body */}
              <div className="px-4 py-3 space-y-2.5">
                <div className="flex items-center gap-2 text-[12px] text-[var(--ink-muted)]">
                  <Camera className="h-3.5 w-3.5 text-[var(--ink-faint)] shrink-0" />
                  <span className="font-mono text-[11.5px]">{room.cameraId}</span>
                </div>
                <div className="flex items-center justify-between text-[12px]">
                  <div className="flex items-center gap-2 text-[var(--ink-muted)]">
                    <Users className="h-3.5 w-3.5 text-[var(--ink-faint)] shrink-0" />
                    <span>Capacity: <span className="font-semibold text-[var(--ink)]">{room.capacity}</span></span>
                  </div>
                  {room.status === "ONLINE" && (
                    <span className="text-[11px] text-[var(--status-present)] font-medium">
                      {room.activeStudents} active
                    </span>
                  )}
                </div>
                <div className="text-[11.5px] text-[var(--ink-faint)] pt-0.5 border-t border-[var(--stone-100)]">
                  {room.assignedFaculty}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
