"use client";

import React, { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileText, FolderArchive, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorNotice } from "@/components/common/async-state";
import { Field } from "@/components/common/field";
import { classroomService } from "@/services/classroom";
import { studentService } from "@/services/student";

const HEADER = "student_name, roll_no, class_id, image_filename, image_url";

export default function ImportPage() {
  const csvInput = useRef<HTMLInputElement>(null);
  const zipInput = useRef<HTMLInputElement>(null);
  const [csv, setCsv] = useState<File | null>(null);
  const [images, setImages] = useState<File | null>(null);
  const [classId, setClassId] = useState("");
  const [dryRun, setDryRun] = useState(true);

  const classrooms = useQuery({
    queryKey: ["classrooms"],
    queryFn: () => classroomService.listClassrooms({ limit: 200 }),
  });

  const run = useMutation({
    mutationFn: () =>
      studentService.importRoster({ csv: csv!, images, classId: classId || undefined, dryRun }),
  });

  const report = run.data;

  return (
    <div className="space-y-7">
      <div>
        <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Bulk Import</h1>
        <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
          Register a whole roster from a CSV. Valid rows are committed, invalid rows are reported.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="rounded-xl border border-[var(--stone-200)] bg-white p-5 space-y-4 shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
          <Field label="Roster CSV" hint={`Header required: ${HEADER}`}>
            <input
              ref={csvInput}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(event) => setCsv(event.target.files?.[0] ?? null)}
            />
            <Button variant="secondary" size="sm" onClick={() => csvInput.current?.click()}>
              <FileText className="h-3.5 w-3.5 mr-1.5" />
              {csv ? csv.name : "Choose CSV"}
            </Button>
          </Field>

          <Field label="Images archive" hint="Optional ZIP holding the files named by image_filename.">
            <input
              ref={zipInput}
              type="file"
              accept=".zip,application/zip"
              className="hidden"
              onChange={(event) => setImages(event.target.files?.[0] ?? null)}
            />
            <Button variant="secondary" size="sm" onClick={() => zipInput.current?.click()}>
              <FolderArchive className="h-3.5 w-3.5 mr-1.5" />
              {images ? images.name : "Choose ZIP"}
            </Button>
          </Field>

          <Field label="Classroom" hint="Overrides the class_id column for every row.">
            <Select value={classId} onChange={(event) => setClassId(event.target.value)}>
              <option value="">Use the CSV column</option>
              {classrooms.data?.items.map((room) => (
                <option key={room.class_id} value={room.class_id}>
                  {room.class_name} · {room.department}
                </option>
              ))}
            </Select>
          </Field>

          <div className="flex items-center justify-between pt-1">
            <div>
              <p className="text-[12px] font-semibold text-[var(--ink)]">Dry run</p>
              <p className="text-[10.5px] text-[var(--ink-faint)]">Validate only: no writes, no uploads.</p>
            </div>
            <Switch checked={dryRun} onCheckedChange={setDryRun} />
          </div>

          <Button
            variant="primary"
            size="sm"
            className="w-full"
            disabled={!csv}
            isLoading={run.isPending}
            onClick={() => run.mutate()}
          >
            <Upload className="h-3.5 w-3.5 mr-1.5" />
            {dryRun ? "Validate" : "Import"}
          </Button>
        </div>

        <div className="space-y-4">
          {run.error ? <ErrorNotice error={run.error} /> : null}
          {report ? (
            <div className="rounded-xl border border-[var(--stone-200)] bg-white p-5 shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
                  Report
                </h2>
                <Badge variant={report.dry_run ? "default" : "present"}>
                  {report.dry_run ? "DRY RUN" : "COMMITTED"}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-3 text-[12px]">
                <Stat label="Rows received" value={report.received_rows} />
                <Stat label="Created" value={report.created} />
                <Stat label="Skipped" value={report.skipped} />
                <Stat label="Images uploaded" value={report.uploaded_images} />
              </div>
            </div>
          ) : null}

          {report && report.errors.length > 0 ? (
            <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Row</TableHead>
                    <TableHead>Roll No</TableHead>
                    <TableHead>Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.errors.map((error) => (
                    <TableRow key={`${error.row}-${error.roll_no}`}>
                      <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)]">
                        {error.row}
                      </TableCell>
                      <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)]">
                        {error.roll_no ?? "—"}
                      </TableCell>
                      <TableCell className="text-[11.5px] text-[var(--ink-muted)]">{error.reason}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {report.errors_truncated ? (
                <p className="px-5 py-2.5 text-[11px] text-[var(--ink-faint)] border-t border-[var(--stone-200)]">
                  Further errors were truncated by the backend.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-[var(--stone-100)] px-3 py-2.5">
      <p className="text-[18px] font-bold text-[var(--ink)] leading-none tabular-nums">{value}</p>
      <p className="text-[10.5px] text-[var(--ink-faint)] mt-1">{label}</p>
    </div>
  );
}
