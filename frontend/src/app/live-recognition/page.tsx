"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { Play, Pause, Square, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { WebcamViewport } from "@/components/webcam/webcam-viewport";
import { LiveRecognitionOverlay } from "@/components/webcam/live-recognition-overlay";
import { useWebcam } from "@/hooks/use-webcam";
import { useLiveRecognitionStore } from "@/store/use-live-recognition-store";
import { MOCK_ATTENDANCE_RECORDS } from "@/mock/attendance-mock";
import { Avatar } from "@/components/ui/avatar";

export default function LiveRecognitionPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const webcam = useWebcam();
  const {
    isDetecting,
    isPaused,
    metrics,
    overlays,
    startDetection,
    stopDetection,
    pauseDetection,
    resumeDetection,
    clearResults,
  } = useLiveRecognitionStore();

  const [recognitionLogs] = useState(MOCK_ATTENDANCE_RECORDS);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Live Recognition</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
            Session: CSE-101 &nbsp;·&nbsp;
            Latency: <span className="font-semibold text-[var(--ink)]">{metrics.latencyMs}ms</span> &nbsp;·&nbsp;
            FPS: <span className="font-semibold text-[var(--ink)]">{metrics.fps}</span>
          </p>
        </div>
      </div>

      {/* Webcam viewport */}
      {!mounted ? (
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
          onSwitchCamera={webcam.switchCamera}
          onToggleFullscreen={webcam.toggleFullscreen}
        >
          {isDetecting && !isPaused && <LiveRecognitionOverlay overlays={overlays} />}
        </WebcamViewport>
      )}

      {/* Detection Engine Controls */}
      <div className="flex items-center justify-between px-4 py-3 rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
        <div className="flex items-center gap-2">
          {!isDetecting ? (
            <Button variant="primary" size="sm" onClick={startDetection}>
              <Play className="h-3.5 w-3.5 mr-1.5 fill-current" />
              Start Engine
            </Button>
          ) : isPaused ? (
            <Button variant="primary" size="sm" onClick={resumeDetection}>
              <Play className="h-3.5 w-3.5 mr-1.5 fill-current" />
              Resume
            </Button>
          ) : (
            <Button variant="secondary" size="sm" onClick={pauseDetection}>
              <Pause className="h-3.5 w-3.5 mr-1.5 fill-current" />
              Pause
            </Button>
          )}

          {isDetecting && (
            <Button variant="danger" size="sm" onClick={stopDetection}>
              <Square className="h-3.5 w-3.5 mr-1.5 fill-current" />
              Stop Engine
            </Button>
          )}

          <Button variant="ghost" size="sm" onClick={clearResults} className="text-[var(--ink-faint)]">
            Clear Boxes
          </Button>
        </div>

        <div className="flex items-center gap-5 text-[12px] text-[var(--ink-faint)]">
          <span>Detections: <span className="font-semibold text-[var(--ink)]">{overlays.length}</span></span>
          <span>GPU: <span className="font-semibold text-[var(--ink)]">{metrics.gpuUsage}%</span></span>
        </div>
      </div>

      {/* Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">

        {/* Recognition log */}
        <div className="lg:col-span-7">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">Recognition Log</h2>
            <Link href="/attendance" className="flex items-center gap-1 text-[11.5px] text-[var(--accent)] hover:text-[var(--ink)] transition-colors font-medium">
              History <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
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
                {recognitionLogs.slice(0, 7).map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)] tabular-nums">
                      {new Date(log.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2.5">
                        <Avatar name={log.studentName} size="sm" />
                        <div>
                          <p className="font-medium text-[12.5px] text-[var(--ink)]">{log.studentName}</p>
                          <p className="text-[10.5px] font-mono text-[var(--ink-faint)]">#{log.rollNumber}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="font-semibold text-[12.5px] text-[var(--ink)] tabular-nums">
                      {(log.confidence * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell>
                      <Badge variant={log.status === "PRESENT" ? "present" : log.status === "UNKNOWN" ? "unknown" : "late"}>
                        {log.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {/* Expected Roster */}
        <div className="lg:col-span-5">
          <h2 className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-3">Expected Roster</h2>
          <div className="rounded-xl border border-[var(--stone-200)] bg-white overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)] divide-y divide-[var(--stone-100)]">
            {[
              { name: "Nidhi Mahesh",         roll: "101", time: "09:21 AM", status: "PRESENT" },
              { name: "Varun Aditya",          roll: "102", time: "09:22 AM", status: "PRESENT" },
              { name: "Ishita Sharma",          roll: "104", time: "09:23 AM", status: "PRESENT" },
              { name: "Rayyan Shaikh Ahmed",    roll: "103", time: "Pending",  status: "PENDING" },
              { name: "Aarav Patel",            roll: "105", time: "Pending",  status: "PENDING" },
            ].map((item, idx) => (
              <div key={idx} className="px-4 py-3 flex items-center justify-between hover:bg-[var(--stone-50)] transition-colors">
                <div className="flex items-center gap-2.5">
                  <Avatar name={item.name} size="sm" />
                  <div>
                    <p className="text-[12.5px] font-medium text-[var(--ink)]">{item.name}</p>
                    <p className="text-[10.5px] font-mono text-[var(--ink-faint)]">#{item.roll}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10.5px] text-[var(--ink-faint)]">{item.time}</span>
                  <Badge variant={item.status === "PRESENT" ? "present" : "secondary"}>
                    {item.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
