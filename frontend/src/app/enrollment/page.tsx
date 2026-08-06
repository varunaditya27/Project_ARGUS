"use client";

import React, { useRef, useState } from "react";
import Image from "next/image";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CheckCircle2, Circle, Loader2, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ErrorNotice } from "@/components/common/async-state";
import { Field } from "@/components/common/field";
import { useWebcam } from "@/hooks/use-webcam";
import { classroomService } from "@/services/classroom";
import { studentService } from "@/services/student";
import type { EnrollmentResult } from "@/types";

/** The three calls an enrollment makes, shown as they happen. */
const STEPS = ["Upload photograph", "Create student record", "Build face templates"] as const;

export default function EnrollmentPage() {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const webcam = useWebcam(videoRef, containerRef);

  const [image, setImage] = useState<{ blob: Blob; url: string; name: string } | null>(null);
  const [name, setName] = useState("");
  const [rollNo, setRollNo] = useState("");
  const [classId, setClassId] = useState("");
  const [step, setStep] = useState(-1);
  const [result, setResult] = useState<EnrollmentResult | null>(null);

  const classrooms = useQuery({
    queryKey: ["classrooms"],
    queryFn: () => classroomService.listClassrooms({ limit: 200 }),
  });

  const pick = (blob: Blob, name: string) => {
    if (image) URL.revokeObjectURL(image.url);
    setImage({ blob, url: URL.createObjectURL(blob), name });
    setResult(null);
    setStep(-1);
  };

  const capture = async () => {
    const dataUrl = webcam.captureFrame();
    if (!dataUrl) return;
    pick(await (await fetch(dataUrl)).blob(), "webcam-capture.png");
    webcam.stopCamera();
  };

  const enroll = useMutation({
    mutationFn: async () => {
      if (!image) throw new Error("No photograph selected");
      setStep(0);
      const uploaded = await studentService.uploadImage(image.blob, image.name);
      setStep(1);
      const student = await studentService.createStudent({
        student_name: name.trim(),
        roll_no: Number(rollNo),
        class_id: classId || null,
        image_url: uploaded.url,
      });
      setStep(2);
      // Templates need the models and ChromaDB; the student row survives either way.
      return studentService.enrollFace(student.student_id, image.blob, image.name);
    },
    onSuccess: (enrollment) => {
      setResult(enrollment);
      setStep(STEPS.length);
      queryClient.invalidateQueries({ queryKey: ["students"] });
    },
  });

  const canSubmit = Boolean(image && name.trim() && Number(rollNo) > 0) && !enroll.isPending;

  return (
    <div className="space-y-7">
      <div>
        <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Enrollment</h1>
        <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
          Upload or capture one unmasked, single-person photograph.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--stone-100)] flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
              Photograph
            </span>
            {image ? (
              <button
                onClick={() => {
                  URL.revokeObjectURL(image.url);
                  setImage(null);
                }}
                className="text-[var(--ink-faint)] hover:text-[var(--ink)]"
                title="Clear"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>

          <div className="p-4 space-y-3">
            <div
              ref={containerRef}
              className="relative aspect-video rounded-lg bg-[var(--stone-100)] overflow-hidden flex items-center justify-center"
            >
              {image ? (
                <Image src={image.url} alt="Selected" fill unoptimized className="object-contain" />
              ) : (
                <video
                  ref={videoRef}
                  className={`h-full w-full object-cover ${webcam.isCameraActive ? "" : "hidden"}`}
                  muted
                  playsInline
                />
              )}
              {!image && !webcam.isCameraActive ? (
                <span className="text-[12px] text-[var(--ink-faint)]">No photograph selected</span>
              ) : null}
            </div>

            {webcam.error ? (
              <p className="text-[11.5px] text-[var(--status-absent)]">{webcam.error}</p>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <input
                ref={fileInput}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) pick(file, file.name);
                }}
              />
              <Button variant="secondary" size="sm" onClick={() => fileInput.current?.click()}>
                <Upload className="h-3.5 w-3.5 mr-1.5" />
                Choose file
              </Button>
              {webcam.isCameraActive ? (
                <>
                  <Button variant="primary" size="sm" onClick={capture}>
                    <Camera className="h-3.5 w-3.5 mr-1.5" />
                    Capture
                  </Button>
                  <Button variant="ghost" size="sm" onClick={webcam.stopCamera}>
                    Stop camera
                  </Button>
                </>
              ) : (
                <Button variant="secondary" size="sm" onClick={webcam.startCamera}>
                  <Camera className="h-3.5 w-3.5 mr-1.5" />
                  Use camera
                </Button>
              )}
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--stone-100)]">
            <span className="text-[11px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
              Student
            </span>
          </div>
          <div className="p-4 space-y-4">
            {enroll.error ? <ErrorNotice error={enroll.error} /> : null}
            <Field label="Full name">
              <Input value={name} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field label="Roll number" hint="Whole number, unique across the institution.">
              <Input
                type="number"
                min={1}
                value={rollNo}
                onChange={(event) => setRollNo(event.target.value)}
              />
            </Field>
            <Field label="Classroom">
              <Select value={classId} onChange={(event) => setClassId(event.target.value)}>
                <option value="">Unassigned</option>
                {classrooms.data?.items.map((room) => (
                  <option key={room.class_id} value={room.class_id}>
                    {room.class_name} · {room.department}
                  </option>
                ))}
              </Select>
            </Field>

            <div className="space-y-2 pt-1">
              {STEPS.map((label, index) => (
                <div key={label} className="flex items-center gap-2 text-[12px]">
                  {step > index ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-[var(--status-present)]" />
                  ) : step === index ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--accent)]" />
                  ) : (
                    <Circle className="h-3.5 w-3.5 text-[var(--stone-300)]" />
                  )}
                  <span className={step > index ? "text-[var(--ink)]" : "text-[var(--ink-faint)]"}>
                    {label}
                  </span>
                </div>
              ))}
            </div>

            {result ? (
              <div className="rounded-lg border border-[#A8D8BC] bg-[var(--status-present-bg)] px-3 py-2.5">
                <p className="text-[12px] font-semibold text-[var(--status-present)]">
                  {result.templates_stored} templates stored
                </p>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {result.stored_variants.map((variant) => (
                    <Badge key={variant} variant="secondary">
                      {variant}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            <Button
              variant="primary"
              size="sm"
              className="w-full"
              disabled={!canSubmit}
              isLoading={enroll.isPending}
              onClick={() => enroll.mutate()}
            >
              Enroll student
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
