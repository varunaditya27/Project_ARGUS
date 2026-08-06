"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AsyncState } from "@/components/common/async-state";
import { reportService } from "@/services/report";

const percent = (value: number | null) => (value === null ? "—" : `${value.toFixed(1)}%`);

export default function ReportsPage() {
  const reports = useQuery({ queryKey: ["reports"], queryFn: () => reportService.sessionReports(25) });

  const rows = reports.data ?? [];
  const departments = reportService.byDepartment(rows);
  const chart = rows
    .filter((report) => report.rate !== null)
    .map((report) => ({ name: `${report.session.subject} · ${report.session.date}`, rate: report.rate }));

  return (
    <div className="space-y-7">
      <div>
        <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Reports</h1>
        <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
          Attendance per session, computed from the register the backend holds.
        </p>
      </div>

      <AsyncState
        isLoading={reports.isLoading}
        error={reports.error}
        isEmpty={rows.length === 0}
        emptyLabel="No sessions to report on yet."
      >
        <div className="space-y-7">
          <div className="rounded-xl border border-[var(--stone-200)] bg-white p-5 shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-4">
              Attendance rate by session
            </h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--stone-200)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} hide={chart.length > 8} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
                  <Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} />
                  <Bar dataKey="rate" radius={[3, 3, 0, 0]}>
                    {chart.map((entry, index) => (
                      <Cell
                        key={index}
                        fill={(entry.rate ?? 0) >= 75 ? "var(--status-present)" : "var(--status-late)"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-3">
              By department
            </h2>
            <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Department</TableHead>
                    <TableHead>Sessions</TableHead>
                    <TableHead>Present</TableHead>
                    <TableHead>Absent</TableHead>
                    <TableHead>Rate</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {departments.map((row) => (
                    <TableRow key={row.department}>
                      <TableCell className="font-medium text-[12.5px] text-[var(--ink)]">
                        {row.department}
                      </TableCell>
                      <TableCell className="text-[12px] tabular-nums">{row.sessions}</TableCell>
                      <TableCell className="text-[12px] tabular-nums">{row.present}</TableCell>
                      <TableCell className="text-[12px] tabular-nums">{row.absent}</TableCell>
                      <TableCell className="font-semibold text-[12.5px] tabular-nums">
                        {percent(row.rate)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>

          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-3">
              Sessions
            </h2>
            <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Subject</TableHead>
                    <TableHead>Classroom</TableHead>
                    <TableHead>Present</TableHead>
                    <TableHead>Absent</TableHead>
                    <TableHead>Rate</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((report) => (
                    <TableRow key={report.session.session_id}>
                      <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)]">
                        {report.session.date}
                      </TableCell>
                      <TableCell className="font-medium text-[12.5px] text-[var(--ink)]">
                        {report.session.subject}
                      </TableCell>
                      <TableCell className="text-[12px] text-[var(--ink-muted)]">
                        {report.classroom?.class_name ?? "—"}
                      </TableCell>
                      <TableCell className="text-[12px] tabular-nums">{report.summary.present}</TableCell>
                      <TableCell className="text-[12px] tabular-nums">{report.summary.absent}</TableCell>
                      <TableCell className="font-semibold text-[12.5px] tabular-nums">
                        {percent(report.rate)}
                      </TableCell>
                      <TableCell>
                        <Badge variant={report.session.status === "ACTIVE" ? "present" : "secondary"}>
                          {report.session.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>
      </AsyncState>
    </div>
  );
}
