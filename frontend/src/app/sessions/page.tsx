"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AsyncState, ErrorNotice } from "@/components/common/async-state";
import { Field } from "@/components/common/field";
import { attendanceService } from "@/services/attendance";
import { classroomService } from "@/services/classroom";
import { sessionService } from "@/services/session";
import type { SessionCreate } from "@/types";

const today = () => new Date().toISOString().slice(0, 10);
const BLANK: SessionCreate = {
  class_id: "",
  subject: "",
  faculty: "",
  date: today(),
  start_time: "09:00",
  end_time: "10:00",
};

export default function SessionsPage() {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [draft, setDraft] = useState<SessionCreate>(BLANK);

  const classrooms = useQuery({
    queryKey: ["classrooms"],
    queryFn: () => classroomService.listClassrooms({ limit: 200 }),
  });
  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: () => sessionService.listSessions({ limit: 100 }),
  });

  const rows = sessions.data?.items ?? [];
  // One summary per session: the API has no combined listing endpoint.
  const summaries = useQueries({
    queries: rows.map((session) => ({
      queryKey: ["summary", session.session_id],
      queryFn: () => attendanceService.summary(session.session_id),
    })),
  });

  const roomName = (classId: string) =>
    classrooms.data?.items.find((room) => room.class_id === classId)?.class_name ?? "—";

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["sessions"] });
    queryClient.invalidateQueries({ queryKey: ["summary"] });
  };

  const create = useMutation({
    mutationFn: () => sessionService.createSession(draft),
    onSuccess: () => {
      invalidate();
      setIsOpen(false);
    },
  });
  const close = useMutation({
    mutationFn: (sessionId: string) => sessionService.closeSession(sessionId),
    onSuccess: invalidate,
  });

  return (
    <div className="space-y-7">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Sessions</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
            {rows.filter((row) => row.status === "ACTIVE").length} active of {rows.length}
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            setDraft({ ...BLANK, class_id: classrooms.data?.items[0]?.class_id ?? "" });
            setIsOpen(true);
          }}
        >
          <Plus className="h-3.5 w-3.5 mr-1.5" />
          Open Session
        </Button>
      </div>

      {close.error ? <ErrorNotice error={close.error} /> : null}

      <AsyncState
        isLoading={sessions.isLoading}
        error={sessions.error}
        isEmpty={rows.length === 0}
        emptyLabel="No sessions yet. Open one to start capturing attendance."
      >
        <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Subject</TableHead>
                <TableHead>Classroom</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Window</TableHead>
                <TableHead>Faculty</TableHead>
                <TableHead>Present</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((session, index) => {
                const summary = summaries[index]?.data;
                return (
                  <TableRow key={session.session_id}>
                    <TableCell className="font-medium text-[12.5px] text-[var(--ink)]">
                      {session.subject}
                    </TableCell>
                    <TableCell className="text-[12px] text-[var(--ink-muted)]">
                      {roomName(session.class_id)}
                    </TableCell>
                    <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)]">
                      {session.date}
                    </TableCell>
                    <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)] tabular-nums">
                      {session.start_time.slice(0, 5)} – {session.end_time.slice(0, 5)}
                    </TableCell>
                    <TableCell className="text-[12px] text-[var(--ink-muted)]">{session.faculty}</TableCell>
                    <TableCell className="text-[12px] tabular-nums">
                      <span className="font-semibold text-[var(--ink)]">{summary?.present ?? "—"}</span>
                      <span className="text-[var(--ink-faint)]"> / {summary?.roster_count ?? "—"}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={session.status === "ACTIVE" ? "present" : "secondary"}>
                        {session.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right space-x-2">
                      <Link
                        href={`/attendance?session=${session.session_id}`}
                        className="text-[11.5px] text-[var(--accent)] hover:underline"
                      >
                        Register
                      </Link>
                      {session.status === "ACTIVE" && (
                        <Button
                          variant="danger"
                          size="sm"
                          isLoading={close.isPending && close.variables === session.session_id}
                          onClick={() => close.mutate(session.session_id)}
                        >
                          Close
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </AsyncState>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Open Session</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {create.error ? <ErrorNotice error={create.error} /> : null}
            <Field label="Classroom" hint="A classroom can only have one ACTIVE session at a time.">
              <Select
                value={draft.class_id}
                onChange={(event) => setDraft({ ...draft, class_id: event.target.value })}
              >
                <option value="">Select a classroom</option>
                {classrooms.data?.items.map((room) => (
                  <option key={room.class_id} value={room.class_id}>
                    {room.class_name} · {room.department}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Subject">
              <Input
                value={draft.subject}
                onChange={(event) => setDraft({ ...draft, subject: event.target.value })}
              />
            </Field>
            <Field label="Faculty">
              <Input
                value={draft.faculty}
                onChange={(event) => setDraft({ ...draft, faculty: event.target.value })}
              />
            </Field>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Date">
                <Input
                  type="date"
                  value={draft.date}
                  onChange={(event) => setDraft({ ...draft, date: event.target.value })}
                />
              </Field>
              <Field label="Start">
                <Input
                  type="time"
                  value={draft.start_time}
                  onChange={(event) => setDraft({ ...draft, start_time: event.target.value })}
                />
              </Field>
              <Field label="End">
                <Input
                  type="time"
                  value={draft.end_time}
                  onChange={(event) => setDraft({ ...draft, end_time: event.target.value })}
                />
              </Field>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setIsOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={create.isPending}
              disabled={!draft.class_id || !draft.subject || !draft.faculty}
              onClick={() => create.mutate()}
            >
              Open
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
