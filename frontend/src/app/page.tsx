"use client";

import React from "react";
import Link from "next/link";
import { Video, UserPlus, ArrowRight, TrendingUp, Users, ShieldCheck, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { MOCK_STUDENTS } from "@/mock/students-mock";
import { MOCK_ATTENDANCE_RECORDS } from "@/mock/attendance-mock";
import { MOCK_SESSIONS } from "@/mock/sessions-mock";

const METRICS = [
  {
    label: "Attendance Rate",
    value: "84.2%",
    sub: "Today",
    icon: TrendingUp,
    color: "text-[var(--accent)]",
    bg: "bg-[var(--accent-light)]",
  },
  {
    label: "Recognition Accuracy",
    value: "98.4%",
    sub: "Session avg",
    icon: ShieldCheck,
    color: "text-[var(--status-present)]",
    bg: "bg-[var(--status-present-bg)]",
  },
  {
    label: "Enrolled Students",
    value: String(MOCK_STUDENTS.length * 40),
    sub: "Active",
    icon: Users,
    color: "text-[var(--ink-muted)]",
    bg: "bg-[var(--stone-100)]",
  },
  {
    label: "Flagged Unknowns",
    value: String(MOCK_ATTENDANCE_RECORDS.filter((r) => r.status === "UNKNOWN").length),
    sub: "Requires review",
    icon: Clock,
    color: "text-[var(--status-late)]",
    bg: "bg-[var(--status-late-bg)]",
  },
];

export default function DashboardPage() {
  const activeSession =
    MOCK_SESSIONS.find((s) => s.status === "ACTIVE") || MOCK_SESSIONS[0];

  return (
    <div className="space-y-7">

      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">
            Dashboard
          </h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
            {new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/enrollment">
            <Button variant="outline" size="sm">
              <UserPlus className="h-3.5 w-3.5 mr-1.5" />
              Enroll
            </Button>
          </Link>
          <Link href="/live-recognition">
            <Button variant="default" size="sm">
              <Video className="h-3.5 w-3.5 mr-1.5" />
              Live Feed
            </Button>
          </Link>
        </div>
      </div>

      {/* Active Session Banner */}
      <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)] overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 bg-[var(--ink)] text-white">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-400" />
          </span>
          <span className="text-[11px] font-semibold tracking-widest uppercase">Active Session</span>
        </div>
        <div className="px-5 py-4 flex items-center justify-between flex-wrap gap-4">
          <div>
            <p className="text-[15px] font-semibold text-[var(--ink)] leading-tight">
              {activeSession.courseName}
            </p>
            <p className="text-[12px] text-[var(--ink-faint)] mt-0.5">
              {activeSession.courseCode} &nbsp;·&nbsp; {activeSession.classroom}
            </p>
          </div>
          <div className="flex items-center gap-8">
            <div>
              <p className="text-[9.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-0.5">Verified</p>
              <p className="text-[17px] font-bold text-[var(--ink)]">
                {activeSession.presentCount}
                <span className="text-[13px] font-normal text-[var(--ink-faint)]"> / {activeSession.enrolledStudentsCount}</span>
              </p>
            </div>
            <div>
              <p className="text-[9.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-0.5">Latency</p>
              <p className="text-[17px] font-bold text-[var(--ink)]">14<span className="text-[12px] font-normal text-[var(--ink-faint)]">ms</span></p>
            </div>
          </div>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {METRICS.map((m) => {
          const Icon = m.icon;
          return (
            <div
              key={m.label}
              className="rounded-xl border border-[var(--stone-200)] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(15,27,53,0.05)]"
            >
              <div className="flex items-start justify-between mb-3">
                <span className={`inline-flex h-8 w-8 items-center justify-center rounded-lg ${m.bg}`}>
                  <Icon className={`h-4 w-4 ${m.color}`} />
                </span>
              </div>
              <p className="text-[24px] font-bold text-[var(--ink)] leading-none tracking-tight">{m.value}</p>
              <p className="text-[11px] text-[var(--ink-faint)] mt-1.5">{m.label}</p>
              <p className="text-[10px] text-[var(--stone-400)] mt-0.5">{m.sub}</p>
            </div>
          );
        })}
      </div>

      {/* Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">

        {/* Recognition Log */}
        <div className="lg:col-span-7">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
              Recognition Log
            </h2>
            <Link
              href="/attendance"
              className="flex items-center gap-1 text-[11.5px] text-[var(--accent)] hover:text-[var(--ink)] transition-colors font-medium"
            >
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="rounded-xl border border-[var(--stone-200)] bg-white overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Student</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {MOCK_ATTENDANCE_RECORDS.slice(0, 6).map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="text-[var(--ink-faint)] font-mono text-[11px] tabular-nums">
                      {new Date(log.timestamp).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2.5">
                        <Avatar name={log.studentName} size="sm" />
                        <span className="font-medium text-[12.5px] text-[var(--ink)]">
                          {log.studentName}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="font-semibold text-[var(--ink)] tabular-nums text-[12px]">
                      {(log.confidence * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          log.status === "PRESENT"
                            ? "present"
                            : log.status === "UNKNOWN"
                            ? "unknown"
                            : "late"
                        }
                      >
                        {log.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {/* Recent Enrollments */}
        <div className="lg:col-span-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
              Recent Enrollments
            </h2>
            <Link
              href="/students"
              className="flex items-center gap-1 text-[11.5px] text-[var(--accent)] hover:text-[var(--ink)] transition-colors font-medium"
            >
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="rounded-xl border border-[var(--stone-200)] bg-white overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)] divide-y divide-[var(--stone-100)]">
            {MOCK_STUDENTS.slice(0, 6).map((student) => (
              <div key={student.id} className="px-4 py-3 flex items-center justify-between hover:bg-[var(--stone-50)] transition-colors">
                <div className="flex items-center gap-2.5">
                  <Avatar name={student.name} size="sm" />
                  <div>
                    <p className="text-[12.5px] font-medium text-[var(--ink)] leading-tight">
                      {student.name}
                    </p>
                    <p className="text-[10.5px] text-[var(--ink-faint)] font-mono mt-0.5">
                      #{student.rollNumber}
                    </p>
                  </div>
                </div>
                <Badge variant="secondary">{student.department}</Badge>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
