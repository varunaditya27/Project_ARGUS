"use client";

import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GraduationCap, Plus, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AsyncState, ErrorNotice } from "@/components/common/async-state";
import { Field } from "@/components/common/field";
import { classroomService } from "@/services/classroom";
import type { ClassroomCreate } from "@/types";

const BLANK: ClassroomCreate = { class_name: "", department: "", semester: 1, strength: 0 };

export default function ClassroomsPage() {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [draft, setDraft] = useState<ClassroomCreate>(BLANK);

  const classrooms = useQuery({
    queryKey: ["classrooms"],
    queryFn: () => classroomService.listClassrooms({ limit: 200 }),
  });

  const create = useMutation({
    mutationFn: () => classroomService.createClassroom(draft),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["classrooms"] });
      setIsOpen(false);
      setDraft(BLANK);
    },
  });

  const rooms = classrooms.data?.items ?? [];

  return (
    <div className="space-y-7">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Classrooms</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">{rooms.length} registered</p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setIsOpen(true)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" />
          Add Classroom
        </Button>
      </div>

      <AsyncState
        isLoading={classrooms.isLoading}
        error={classrooms.error}
        isEmpty={rooms.length === 0}
        emptyLabel="No classrooms yet. Add one before enrolling students."
      >
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {rooms.map((room) => (
            <div
              key={room.class_id}
              className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)] overflow-hidden"
            >
              <div className="px-4 py-3 border-b border-[var(--stone-100)] flex items-center justify-between">
                <div className="min-w-0">
                  <p className="text-[13.5px] font-semibold text-[var(--ink)] truncate">{room.class_name}</p>
                  <p className="text-[10.5px] font-mono text-[var(--ink-faint)] mt-0.5 truncate">
                    {room.class_id}
                  </p>
                </div>
                <Badge variant="default">Sem {room.semester}</Badge>
              </div>
              <div className="px-4 py-3 space-y-2.5">
                <div className="flex items-center gap-2 text-[12px] text-[var(--ink-muted)]">
                  <GraduationCap className="h-3.5 w-3.5 text-[var(--ink-faint)] shrink-0" />
                  <span>{room.department}</span>
                </div>
                <div className="flex items-center gap-2 text-[12px] text-[var(--ink-muted)]">
                  <Users className="h-3.5 w-3.5 text-[var(--ink-faint)] shrink-0" />
                  <span>
                    Declared strength: <span className="font-semibold text-[var(--ink)]">{room.strength}</span>
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </AsyncState>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Classroom</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {create.error ? <ErrorNotice error={create.error} /> : null}
            <Field label="Class name">
              <Input
                placeholder="e.g. CSE-A"
                value={draft.class_name}
                onChange={(event) => setDraft({ ...draft, class_name: event.target.value })}
              />
            </Field>
            <Field label="Department">
              <Input
                placeholder="e.g. Computer Science"
                value={draft.department}
                onChange={(event) => setDraft({ ...draft, department: event.target.value })}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Semester">
                <Input
                  type="number"
                  min={1}
                  max={12}
                  value={draft.semester}
                  onChange={(event) => setDraft({ ...draft, semester: Number(event.target.value) })}
                />
              </Field>
              <Field label="Strength">
                <Input
                  type="number"
                  min={0}
                  value={draft.strength}
                  onChange={(event) => setDraft({ ...draft, strength: Number(event.target.value) })}
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
              disabled={!draft.class_name || !draft.department}
              onClick={() => create.mutate()}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}