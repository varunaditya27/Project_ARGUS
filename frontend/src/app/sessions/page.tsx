"use client";

import React, { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { MOCK_SESSIONS } from "@/mock/sessions-mock";
import { SessionStatus } from "@/types";

const sessionBadge = (status: SessionStatus) => {
  switch (status) {
    case "ACTIVE":    return "present" as const;
    case "UPCOMING":  return "default" as const;
    case "COMPLETED": return "secondary" as const;
    case "CANCELLED": return "absent" as const;
  }
};

export default function SessionsPage() {
  const [sessions] = useState(MOCK_SESSIONS);

  return (
    <div className="space-y-7">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Sessions</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">{sessions.length} scheduled sessions</p>
        </div>
        <Button variant="primary" size="sm">
          <Plus className="h-3.5 w-3.5 mr-1.5" />
          Schedule Session
        </Button>
      </div>

      <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Code</TableHead>
              <TableHead>Course</TableHead>
              <TableHead>Classroom</TableHead>
              <TableHead>Time</TableHead>
              <TableHead>Faculty</TableHead>
              <TableHead>Attendance</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sessions.map((sess) => (
              <TableRow key={sess.id}>
                <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)]">
                  {sess.courseCode}
                </TableCell>
                <TableCell className="font-medium text-[12.5px] text-[var(--ink)]">
                  {sess.courseName}
                </TableCell>
                <TableCell className="text-[12px] text-[var(--ink-muted)]">{sess.classroom}</TableCell>
                <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)] tabular-nums">
                  {sess.startTime} – {sess.endTime}
                </TableCell>
                <TableCell className="text-[12px] text-[var(--ink-muted)]">{sess.facultyName}</TableCell>
                <TableCell className="text-[12px] tabular-nums">
                  <span className="font-semibold text-[var(--ink)]">{sess.presentCount}</span>
                  <span className="text-[var(--ink-faint)]"> / {sess.enrolledStudentsCount}</span>
                </TableCell>
                <TableCell>
                  <Badge variant={sessionBadge(sess.status)}>
                    {sess.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
