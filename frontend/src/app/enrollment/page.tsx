"use client";

import React, { useState, useRef, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Upload, CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { WebcamViewport } from "@/components/webcam/webcam-viewport";
import { useWebcam } from "@/hooks/use-webcam";
import { useEnrollmentStore } from "@/store/use-enrollment-store";

const enrollmentSchema = z.object({
  name: z.string().min(2, "Full Name is required."),
  rollNumber: z.string().min(1, "Roll Number is required."),
  email: z.string().email("Valid institutional email is required."),
  department: z.string().min(1, "Department is required."),
  classroom: z.string().optional(),
});

type EnrollmentFormData = z.infer<typeof enrollmentSchema>;

export default function EnrollmentPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const webcam = useWebcam();
  const [snapshotPreview, setSnapshotPreview] = useState<string | null>(null);
  const {
    capturedImageName,
    processingSteps,
    isProcessing,
    isComplete,
    setCapturedImage,
    startEnrollmentProcess,
    resetEnrollment,
  } = useEnrollmentStore();

  const [activeSourceTab, setActiveSourceTab] = useState<"webcam" | "upload">("webcam");
  const [dragActive, setDragActive] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    register,
    handleSubmit,
    reset: resetForm,
    formState: { errors },
  } = useForm<EnrollmentFormData>({
    resolver: zodResolver(enrollmentSchema),
    defaultValues: {
      name: "",
      rollNumber: "",
      email: "",
      department: "Computer Science & Eng.",
      classroom: "CSE-101",
    },
  });

  const handleCapture = () => {
    const dataUrl = webcam.captureFrame();
    if (dataUrl) {
      setSnapshotPreview(dataUrl);
      setCapturedImage(`snapshot_${Date.now()}.png`);
    }
  };

  const clearSnapshot = () => {
    setSnapshotPreview(null);
    setCapturedImage(null);
  };

  const handleFileUpload = (file: File) => {
    setCapturedImage(file.name);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
  };

  const clearUpload = () => {
    setCapturedImage(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const onSubmit = (data: EnrollmentFormData) => {
    if (!capturedImageName) {
      setCapturedImage("webcam_snapshot_default.png");
    }
    startEnrollmentProcess();
  };

  const handleReset = () => {
    resetForm();
    resetEnrollment();
  };

  return (
    <div className="space-y-7">
      {/* Page Header */}
      <div>
        <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Enrollment</h1>
        <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">Register a new student into the recognition system</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Side: Camera/Upload Viewport */}
        <div className="lg:col-span-7 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
              Facial Input Source
            </span>

            <div className="flex gap-0.5 border border-[var(--stone-300)] rounded-md p-0.5 text-[11.5px]">
              <button
                type="button"
                onClick={() => setActiveSourceTab("webcam")}
                className={`px-3 py-1 rounded transition-all ${
                  activeSourceTab === "webcam"
                    ? "bg-[var(--ink)] text-white font-semibold"
                    : "text-[var(--ink-faint)] hover:text-[var(--ink)]"
                }`}
              >
                Webcam
              </button>
              <button
                type="button"
                onClick={() => setActiveSourceTab("upload")}
                className={`px-3 py-1 rounded transition-all ${
                  activeSourceTab === "upload"
                    ? "bg-[var(--ink)] text-white font-semibold"
                    : "text-[var(--ink-faint)] hover:text-[var(--ink)]"
                }`}
              >
                Upload Image
              </button>
            </div>
          </div>

          {activeSourceTab === "webcam" ? (
            <div className="space-y-3">
              {!mounted ? (
                /* SSR placeholder — exact same dimensions so no layout shift */
                <div className="aspect-video w-full rounded-xl bg-[#0A0C10] border border-[#1E2330] flex items-center justify-center">
                  <span className="text-[12px] text-white/20">Initializing camera…</span>
                </div>
              ) : (
                <WebcamViewport
                  isCameraActive={webcam.isCameraActive}
                  permissionStatus={webcam.permissionStatus}
                  resolution={webcam.resolution}
                  fps={webcam.fps}
                  devices={webcam.devices}
                  selectedDeviceId={webcam.selectedDeviceId}
                  selectedDeviceLabel={webcam.selectedDeviceLabel}
                  isFullscreen={webcam.isFullscreen}
                  error={webcam.error}
                  containerRef={webcam.containerRef}
                  videoRef={webcam.videoRef}
                  onStartCamera={webcam.startCamera}
                  onStopCamera={webcam.stopCamera}
                  onCapture={handleCapture}
                  onSwitchCamera={webcam.switchCamera}
                  onToggleFullscreen={webcam.toggleFullscreen}
                />
              )}

              {/* Snapshot preview */}
              {snapshotPreview && (
                <div className="relative rounded-xl overflow-hidden border border-[var(--stone-200)] bg-[var(--stone-50)]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={snapshotPreview} alt="Captured snapshot" className="w-full object-contain max-h-48" />
                  <div className="absolute bottom-0 inset-x-0 bg-white/90 backdrop-blur-sm border-t border-[var(--stone-200)] px-4 py-2 flex items-center justify-between">
                    <span className="text-[11.5px] font-medium text-[var(--ink)]">Snapshot captured</span>
                    <div className="flex items-center gap-2">
                      <button onClick={handleCapture} className="text-[11.5px] text-[var(--accent)] font-medium hover:text-[var(--ink)] transition-colors">
                        Retake
                      </button>
                      <button onClick={clearSnapshot} className="text-[11.5px] text-[var(--ink-faint)] hover:text-[var(--status-absent)] transition-colors font-medium">
                        Remove
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (


            /* ── Upload Tab ── */
            <div className="space-y-3">
              {previewUrl ? (
                /* Image Preview */
                <div className="relative rounded-xl overflow-hidden border border-[var(--stone-200)] bg-[var(--stone-50)]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={previewUrl}
                    alt="Uploaded preview"
                    className="w-full object-contain max-h-72"
                  />
                  <div className="absolute bottom-0 inset-x-0 bg-white/90 backdrop-blur-sm border-t border-[var(--stone-200)] px-4 py-2.5 flex items-center justify-between">
                    <span className="text-[12px] font-medium text-[var(--ink)] truncate max-w-[60%]">
                      {capturedImageName}
                    </span>
                    <div className="flex items-center gap-2">
                      <label className="cursor-pointer text-[11.5px] text-[var(--accent)] font-medium hover:text-[var(--ink)] transition-colors">
                        Replace
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept="image/*"
                          className="hidden"
                          onChange={(e) => {
                            if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
                          }}
                        />
                      </label>
                      <button
                        onClick={clearUpload}
                        className="text-[11.5px] text-[var(--ink-faint)] hover:text-[var(--status-absent)] transition-colors font-medium"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                /* Drop Zone */
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragActive(false);
                    if (e.dataTransfer.files?.[0]) handleFileUpload(e.dataTransfer.files[0]);
                  }}
                  onClick={() => fileInputRef.current?.click()}
                  className={`flex flex-col items-center justify-center gap-3 py-14 px-8 border-2 border-dashed rounded-xl text-center select-none cursor-pointer transition-colors ${
                    dragActive
                      ? "border-[var(--accent)] bg-[var(--accent-light)]"
                      : "border-[var(--stone-300)] bg-[var(--stone-50)] hover:border-[var(--accent-muted)] hover:bg-[var(--accent-light)]"
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
                    }}
                  />
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--stone-100)] border border-[var(--stone-200)]">
                    <Upload className="h-5 w-5 text-[var(--ink-faint)]" />
                  </div>
                  <div>
                    <p className="text-[13px] font-semibold text-[var(--ink)]">Drop image here</p>
                    <p className="text-[11.5px] text-[var(--ink-faint)] mt-0.5">or click to browse — JPG, PNG, WEBP</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Side: Form */}
        <div className="lg:col-span-5 space-y-5">
          <form id="enroll-form" onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <p className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
              Student Information
            </p>

            <div className="space-y-1.5">
              <label className="text-[12px] font-semibold text-[var(--ink)]">Full Name *</label>
              <Input placeholder="Nidhi Mahesh" {...register("name")} />
              {errors.name && <p className="text-[11px] text-[var(--status-absent)]">{errors.name.message}</p>}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-[12px] font-semibold text-[var(--ink)]">Roll Number *</label>
                <Input placeholder="101" {...register("rollNumber")} />
                {errors.rollNumber && <p className="text-[11px] text-[var(--status-absent)]">{errors.rollNumber.message}</p>}
              </div>
              <div className="space-y-1.5">
                <label className="text-[12px] font-semibold text-[var(--ink)]">Section</label>
                <Select {...register("classroom")}>
                  <option value="CSE-101">CSE-101</option>
                  <option value="AI-Lab">AI-Lab</option>
                  <option value="ECE-204">ECE-204</option>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-[12px] font-semibold text-[var(--ink)]">Email *</label>
              <Input placeholder="nidhi.m@argus.edu" {...register("email")} />
              {errors.email && <p className="text-[11px] text-[var(--status-absent)]">{errors.email.message}</p>}
            </div>

            <div className="space-y-1.5">
              <label className="text-[12px] font-semibold text-[var(--ink)]">Department *</label>
              <Select {...register("department")}>
                <option value="Computer Science & Eng.">Computer Science & Eng.</option>
                <option value="Artificial Intelligence">Artificial Intelligence</option>
                <option value="Electronics & Comm.">Electronics & Comm.</option>
              </Select>
            </div>

            <div className="pt-3 flex items-center justify-between border-t border-[var(--stone-200)]">
              <Button type="button" variant="ghost" size="sm" onClick={handleReset}>
                Reset
              </Button>
              <Button type="submit" form="enroll-form" variant="primary" size="sm" isLoading={isProcessing}>
                Submit Enrollment
              </Button>
            </div>
          </form>

          {/* Pipeline Status */}
          <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)] overflow-hidden">
            <div className="px-4 py-3 border-b border-[var(--stone-100)] flex items-center justify-between">
              <span className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
                Pipeline Status
              </span>
              {isComplete && <Badge variant="present">Complete</Badge>}
            </div>
            <div className="divide-y divide-[var(--stone-100)]">
              {processingSteps.map((step) => (
                <div key={step.id} className="px-4 py-2.5 flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    {step.status === "completed" ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-[var(--status-present)] shrink-0" />
                    ) : step.status === "processing" ? (
                      <Loader2 className="h-3.5 w-3.5 text-[var(--accent)] animate-spin shrink-0" />
                    ) : (
                      <div className="h-3.5 w-3.5 rounded-full border border-[var(--stone-300)] shrink-0" />
                    )}
                    <span className="text-[12.5px] text-[var(--ink)]">{step.label}</span>
                  </div>
                  <span className="text-[10.5px] text-[var(--ink-faint)] capitalize">{step.status}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
