"use client";

import React, { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { FileSpreadsheet } from "lucide-react";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AsyncState } from "@/components/common/async-state";
import { attendanceService } from "@/services/attendance";
import { sessionService } from "@/services/session";
import type { AttendanceStatus } from "@/types";

export default function AttendancePage() {
  // useSearchParams needs a boundary; the register is client-fetched anyway.
  return (
    <Suspense fallback={null}>
      <AttendanceView />
    </Suspense>
  );
}

function AttendanceView() {
  const params = useSearchParams();
  const [selected, setSelected] = useState(params.get("session") ?? "");
  const [status, setStatus] = useState<AttendanceStatus | "">("");
  const [isExporting, setIsExporting] = useState(false);

  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: () => sessionService.listSessions({ limit: 100 }),
  });

  // Fall back to the newest session so the page is never empty on first open.
  const sessionId = selected || sessions.data?.items[0]?.session_id || "";

  const register = useQuery({
    queryKey: ["register", sessionId, status],
    queryFn: () =>
      attendanceService.register(sessionId, { status: status || undefined, limit: 200 }),
    enabled: Boolean(sessionId),
  });
  const summary = useQuery({
    queryKey: ["summary", sessionId],
    queryFn: () => attendanceService.summary(sessionId),
    enabled: Boolean(sessionId),
  });

  const exportCsv = async () => {
    setIsExporting(true);
    try {
      const rows = await attendanceService.registerAll(sessionId);
      const blob = new Blob([attendanceService.toCsv(rows)], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `attendance_${sessionId}.csv`;
      link.click();
      URL.revokeObjectURL(link.href);
    } finally {
      setIsExporting(false);
    }
  };

  const rows = register.data?.items ?? [];

  return (
    <div className="space-y-7">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Attendance</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
            {summary.data
              ? `${summary.data.present} present · ${summary.data.absent} absent · roster ${summary.data.roster_count}`
              : "Select a session"}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={exportCsv}
          isLoading={isExporting}
          disabled={!sessionId}
        >
          <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5" />
          Export CSV
        </Button>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <Select value={sessionId} onChange={(event) => setSelected(event.target.value)} className="w-96">
          <option value="">Select a session</option>
          {sessions.data?.items.map((session) => (
            <option key={session.session_id} value={session.session_id}>
              {session.date} · {session.subject} ({session.status})
            </option>
          ))}
        </Select>
        <Select
          value={status}
          onChange={(event) => setStatus(event.target.value as AttendanceStatus | "")}
          className="w-40"
        >
          <option value="">All statuses</option>
          <option value="PRESENT">Present</option>
          <option value="ABSENT">Absent</option>
        </Select>
      </div>

      <AsyncState
        isLoading={Boolean(sessionId) && register.isLoading}
        error={register.error}
        isEmpty={!sessionId || rows.length === 0}
        emptyLabel={
          sessionId
            ? "No rows yet. Absent rows are written when the session is closed."
            : "Pick a session to see its register."
        }
      >
        <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Roll No</TableHead>
                <TableHead>Student</TableHead>
                <TableHead>First seen</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((record) => (
                <TableRow key={record.attendance_id}>
                  <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)] tabular-nums">
                    {record.roll_no}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <Avatar name={record.student_name} size="sm" />
                      <span className="font-medium text-[12.5px] text-[var(--ink)]">
                        {record.student_name}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)] tabular-nums">
                    {record.status === "PRESENT"
                      ? new Date(record.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })
                      : "—"}
                  </TableCell>
                  <TableCell className="font-semibold text-[12.5px] text-[var(--ink)] tabular-nums">
                    {record.confidence > 0 ? `${(record.confidence * 100).toFixed(1)}%` : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={record.status === "PRESENT" ? "present" : "absent"}>
                      {record.status}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </AsyncState>
    </div>
  );
}
