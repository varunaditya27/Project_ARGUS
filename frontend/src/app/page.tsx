"use client";

import React from "react";
import Link from "next/link";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, UserPlus, Users, Video, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AsyncState } from "@/components/common/async-state";
import { attendanceService } from "@/services/attendance";
import { classroomService } from "@/services/classroom";
import { recognitionService } from "@/services/recognition";
import { sessionService } from "@/services/session";

export default function DashboardPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: () => recognitionService.health() });
  const models = useQuery({ queryKey: ["models"], queryFn: () => recognitionService.models() });
  const classrooms = useQuery({
    queryKey: ["classrooms"],
    queryFn: () => classroomService.listClassrooms({ limit: 200 }),
  });
  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: () => sessionService.listSessions({ limit: 20 }),
  });

  const rows = sessions.data?.items ?? [];
  const active = rows.filter((session) => session.status === "ACTIVE");
  const summaries = useQueries({
    queries: active.map((session) => ({
      queryKey: ["summary", session.session_id],
      queryFn: () => attendanceService.summary(session.session_id),
    })),
  });

  const present = summaries.reduce((total, query) => total + (query.data?.present ?? 0), 0);
  const roster = summaries.reduce((total, query) => total + (query.data?.roster_count ?? 0), 0);

  return (
    <div className="space-y-7">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Dashboard</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
            {new Date().toLocaleDateString("en-GB", {
              weekday: "long",
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
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

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Metric
          label="Active sessions"
          value={String(active.length)}
          sub={`${rows.length} total`}
          icon={<Video className="h-4 w-4 text-[var(--accent)]" />}
          bg="bg-[var(--accent-light)]"
        />
        <Metric
          label="Present now"
          value={roster > 0 ? `${present} / ${roster}` : "—"}
          sub="Across active sessions"
          icon={<Users className="h-4 w-4 text-[var(--status-present)]" />}
          bg="bg-[var(--status-present-bg)]"
        />
        <Metric
          label="Classrooms"
          value={String(classrooms.data?.items.length ?? 0)}
          sub="Registered"
          icon={<Users className="h-4 w-4 text-[var(--ink-muted)]" />}
          bg="bg-[var(--stone-100)]"
        />
        <Metric
          label="Recognition"
          value={models.data?.recognition_ready ? "Ready" : "Not ready"}
          sub={models.data?.recognition_ready ? "Thresholds calibrated" : "Frames are refused"}
          icon={
            models.data?.recognition_ready ? (
              <CheckCircle2 className="h-4 w-4 text-[var(--status-present)]" />
            ) : (
              <XCircle className="h-4 w-4 text-[var(--status-late)]" />
            )
          }
          bg={models.data?.recognition_ready ? "bg-[var(--status-present-bg)]" : "bg-[var(--status-late-bg)]"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <div className="lg:col-span-7">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
              Recent sessions
            </h2>
            <Link
              href="/sessions"
              className="flex items-center gap-1 text-[11.5px] text-[var(--accent)] hover:text-[var(--ink)] font-medium"
            >
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <AsyncState
            isLoading={sessions.isLoading}
            error={sessions.error}
            isEmpty={rows.length === 0}
            emptyLabel="No sessions yet."
          >
            <div className="rounded-xl border border-[var(--stone-200)] bg-white overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Subject</TableHead>
                    <TableHead>Faculty</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.slice(0, 6).map((session) => (
                    <TableRow key={session.session_id}>
                      <TableCell className="font-mono text-[11px] text-[var(--ink-faint)]">
                        {session.date}
                      </TableCell>
                      <TableCell className="font-medium text-[12.5px] text-[var(--ink)]">
                        {session.subject}
                      </TableCell>
                      <TableCell className="text-[12px] text-[var(--ink-muted)]">
                        {session.faculty}
                      </TableCell>
                      <TableCell>
                        <Badge variant={session.status === "ACTIVE" ? "present" : "secondary"}>
                          {session.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </AsyncState>
        </div>

        <div className="lg:col-span-5">
          <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-3">
            Dependencies
          </h2>
          <div className="rounded-xl border border-[var(--stone-200)] bg-white overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)] divide-y divide-[var(--stone-100)]">
            {(health.data?.checks ?? []).map((check) => (
              <Row key={check.name} label={check.name} detail={check.detail} ok={check.healthy} />
            ))}
            {(models.data?.components ?? []).map((component) => (
              <Row
                key={component.name}
                label={component.name}
                detail={component.detail}
                ok={component.configured}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  icon,
  bg,
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  bg: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--stone-200)] bg-white px-5 py-4 shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
      <span className={`inline-flex h-8 w-8 items-center justify-center rounded-lg mb-3 ${bg}`}>{icon}</span>
      <p className="text-[24px] font-bold text-[var(--ink)] leading-none tracking-tight">{value}</p>
      <p className="text-[11px] text-[var(--ink-faint)] mt-1.5">{label}</p>
      <p className="text-[10px] text-[var(--stone-400)] mt-0.5">{sub}</p>
    </div>
  );
}

function Row({ label, detail, ok }: { label: string; detail: string; ok: boolean }) {
  return (
    <div className="px-4 py-3 flex items-center justify-between gap-3">
      <div className="min-w-0">
        <p className="text-[12.5px] font-medium text-[var(--ink)]">{label}</p>
        <p className="text-[10.5px] text-[var(--ink-faint)] truncate">{detail}</p>
      </div>
      <Badge variant={ok ? "present" : "unknown"}>{ok ? "OK" : "MISSING"}</Badge>
    </div>
  );
}
