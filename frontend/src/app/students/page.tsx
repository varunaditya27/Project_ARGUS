"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Trash2, UserPlus } from "lucide-react";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AsyncState, ErrorNotice } from "@/components/common/async-state";
import { classroomService } from "@/services/classroom";
import { studentService } from "@/services/student";

const PAGE_SIZE = 50;

export default function StudentsPage() {
  const queryClient = useQueryClient();
  const [classId, setClassId] = useState("");
  // Keyset cursors: one roll_no per page visited, so Back is exact.
  const [cursors, setCursors] = useState<(number | undefined)[]>([undefined]);
  const [pageIndex, setPageIndex] = useState(0);

  const classrooms = useQuery({
    queryKey: ["classrooms"],
    queryFn: () => classroomService.listClassrooms({ limit: 200 }),
  });

  const after = cursors[pageIndex];
  const students = useQuery({
    queryKey: ["students", classId, after],
    queryFn: () => studentService.listStudents({ classId: classId || undefined, after, limit: PAGE_SIZE }),
  });

  const remove = useMutation({
    mutationFn: (studentId: string) => studentService.deleteStudent(studentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["students"] }),
  });

  const rows = students.data?.items ?? [];
  const nextCursor = students.data?.next_cursor ?? null;

  const roomName = (id: string | null) =>
    classrooms.data?.items.find((room) => room.class_id === id)?.class_name ?? "Unassigned";

  const resetPaging = (value: string) => {
    setClassId(value);
    setCursors([undefined]);
    setPageIndex(0);
  };

  const goForward = () => {
    if (nextCursor === null) return;
    setCursors((previous) => {
      const next = previous.slice(0, pageIndex + 1);
      next.push(nextCursor);
      return next;
    });
    setPageIndex((index) => index + 1);
  };

  return (
    <div className="space-y-7">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Students</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
            {rows.length} on this page{nextCursor !== null ? ", more available" : ""}
          </p>
        </div>
        <Link href="/enrollment">
          <Button variant="primary" size="sm">
            <UserPlus className="h-3.5 w-3.5 mr-1.5" />
            Enroll Student
          </Button>
        </Link>
      </div>

      <Select value={classId} onChange={(event) => resetPaging(event.target.value)} className="w-64">
        <option value="">All classrooms</option>
        {classrooms.data?.items.map((room) => (
          <option key={room.class_id} value={room.class_id}>
            {room.class_name} · {room.department}
          </option>
        ))}
      </Select>

      {remove.error ? <ErrorNotice error={remove.error} /> : null}

      <AsyncState
        isLoading={students.isLoading}
        error={students.error}
        isEmpty={rows.length === 0}
        emptyLabel="No students on the roster yet."
      >
        <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Roll No</TableHead>
                <TableHead>Student</TableHead>
                <TableHead>Classroom</TableHead>
                <TableHead>Enrolled</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((student) => (
                <TableRow key={student.student_id}>
                  <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)] tabular-nums">
                    {student.roll_no}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <Avatar name={student.student_name} size="sm" />
                      <span className="font-medium text-[12.5px] text-[var(--ink)]">
                        {student.student_name}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-[12px] text-[var(--ink-muted)]">
                    {roomName(student.class_id)}
                  </TableCell>
                  <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)]">
                    {new Date(student.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <button
                      onClick={() => remove.mutate(student.student_id)}
                      className="text-[var(--ink-faint)] hover:text-[var(--status-absent)] transition-colors p-1 rounded"
                      title="Remove student, templates and attendance"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="px-5 py-3 flex items-center justify-between border-t border-[var(--stone-200)]">
            <span className="text-[11.5px] text-[var(--ink-faint)]">Page {pageIndex + 1}</span>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="icon"
                disabled={pageIndex === 0}
                onClick={() => setPageIndex((index) => Math.max(0, index - 1))}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <Button variant="outline" size="icon" disabled={nextCursor === null} onClick={goForward}>
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </AsyncState>
    </div>
  );
}
