"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Play, Square } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorNotice } from "@/components/common/async-state";
import { LiveRecognitionOverlay } from "@/components/webcam/live-recognition-overlay";
import { WebcamViewport } from "@/components/webcam/webcam-viewport";
import { useWebcam } from "@/hooks/use-webcam";
import { recognitionService } from "@/services/recognition";
import { sessionService } from "@/services/session";
import { studentService } from "@/services/student";
import type { FaceDecision } from "@/types";

/** Frames are sent one at a time; this is the pause between round trips. */
const FRAME_INTERVAL_MS = 700;

export default function LiveRecognitionPage() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const webcam = useWebcam(videoRef, containerRef);
  const [sessionId, setSessionId] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [faces, setFaces] = useState<FaceDecision[]>([]);
  const [frameSize, setFrameSize] = useState({ width: 0, height: 0 });
  const [latency, setLatency] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const frameNumber = useRef(0);
  const running = useRef(false);

  const models = useQuery({ queryKey: ["models"], queryFn: () => recognitionService.models() });
  const sessions = useQuery({
    queryKey: ["sessions", "ACTIVE"],
    queryFn: () => sessionService.listSessions({ status: "ACTIVE", limit: 50 }),
  });

  const session = sessions.data?.items.find((item) => item.session_id === sessionId);
  const roster = useQuery({
    queryKey: ["students", session?.class_id ?? "all"],
    queryFn: () => studentService.listStudents({ classId: session?.class_id || undefined, limit: 500 }),
  });

  const [fetchedNames, setFetchedNames] = useState<Record<string, string>>({});

  useEffect(() => {
    const missingIds = faces
      .map((f) => f.student_id)
      .filter(
        (id): id is string =>
          typeof id === "string" &&
          Boolean(id) &&
          !fetchedNames[id] &&
          !roster.data?.items.some((student) => student.student_id === id)
      );

    if (missingIds.length === 0) return;

    missingIds.forEach((id) => {
      studentService
        .getStudent(id)
        .then((student) => {
          setFetchedNames((prev) => ({ ...prev, [id]: student.student_name }));
        })
        .catch(() => {
          setFetchedNames((prev) => ({ ...prev, [id]: "Unknown Student" }));
        });
    });
  }, [faces, roster.data, fetchedNames]);

  const nameFor = useCallback(
    (studentId: string | null) => {
      if (!studentId) return "Unknown";
      const id: string = studentId;
      const fromRoster = roster.data?.items.find((student) => student.student_id === id)?.student_name;
      if (fromRoster) return fromRoster;
      if (fetchedNames[id]) return fetchedNames[id];
      return "Resolving...";
    },
    [roster.data, fetchedNames]
  );

  // One frame in flight at a time, so a slow reply cannot build a backlog.
  useEffect(() => {
    if (!isRunning) return;
    running.current = true;
    let timer: ReturnType<typeof setTimeout>;

    const grabFrame = async (): Promise<Blob | null> => {
      const video = videoRef.current;
      if (!video?.videoWidth) return null;
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d")?.drawImage(video, 0, 0);
      setFrameSize({ width: canvas.width, height: canvas.height });
      return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
    };

    const loop = async () => {
      while (running.current) {
        const frame = await grabFrame();
        if (frame) {
          const startedAt = performance.now();
          try {
            frameNumber.current += 1;
            const result = await recognitionService.recognizeFrame(
              frame,
              sessionId || undefined,
              `frame-${frameNumber.current.toString().padStart(6, "0")}`
            );
            setFaces(result.faces);
            setLatency(Math.round(performance.now() - startedAt));
            setError(null);
          } catch (caught) {
            setError(caught);
            running.current = false;
            setIsRunning(false);
            return;
          }
        }
        await new Promise((resolve) => {
          timer = setTimeout(resolve, FRAME_INTERVAL_MS);
        });
      }
    };
    void loop();

    return () => {
      running.current = false;
      clearTimeout(timer);
    };
  }, [isRunning, sessionId, videoRef]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">
            Live Recognition
          </h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
            {latency !== null ? `Round trip: ${latency} ms · ` : ""}
            {faces.length} face{faces.length === 1 ? "" : "s"} in the last frame
          </p>
        </div>
        <Select
          value={sessionId}
          onChange={(event) => setSessionId(event.target.value)}
          className="w-80"
          disabled={isRunning}
        >
          <option value="">No session (recognise only, nothing recorded)</option>
          {sessions.data?.items.map((item) => (
            <option key={item.session_id} value={item.session_id}>
              {item.subject} · {item.date}
            </option>
          ))}
        </Select>
      </div>

      {models.data && !models.data.recognition_ready ? (
        <div className="rounded-xl border border-[#DDCBA0] bg-[var(--status-late-bg)] px-4 py-3 flex items-start gap-2.5">
          <AlertTriangle className="h-4 w-4 text-[var(--status-late)] shrink-0 mt-0.5" />
          <p className="text-[12px] text-[var(--ink-muted)]">
            The recognition stack is not ready, so the API will refuse frames instead of guessing.
            Missing:{" "}
            {models.data.components
              .filter((component) => !component.configured)
              .map((component) => component.name)
              .join(", ") || "calibrated thresholds"}
            .
          </p>
        </div>
      ) : null}

      {error ? <ErrorNotice error={error} /> : null}

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
        containerRef={containerRef}
        videoRef={videoRef}
        onStartCamera={webcam.startCamera}
        onStopCamera={webcam.stopCamera}
        onSwitchCamera={webcam.switchCamera}
        onToggleFullscreen={webcam.toggleFullscreen}
      >
        {isRunning ? (
          <LiveRecognitionOverlay
            faces={faces}
            frameWidth={frameSize.width}
            frameHeight={frameSize.height}
            labelFor={(face) => (face.student_id ? nameFor(face.student_id) : face.state)}
          />
        ) : null}
      </WebcamViewport>

      <div className="flex items-center justify-between px-4 py-3 rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
        {isRunning ? (
          <Button variant="danger" size="sm" onClick={() => setIsRunning(false)}>
            <Square className="h-3.5 w-3.5 mr-1.5 fill-current" />
            Stop
          </Button>
        ) : (
          <Button
            variant="primary"
            size="sm"
            disabled={!webcam.isCameraActive}
            onClick={() => setIsRunning(true)}
          >
            <Play className="h-3.5 w-3.5 mr-1.5 fill-current" />
            Start recognising
          </Button>
        )}
        <span className="text-[11.5px] text-[var(--ink-faint)]">
          {sessionId
            ? "Matches are buffered and written on the capture interval."
            : "Pick a session to record attendance."}
        </span>
      </div>

      <div>
        <h2 className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-3">
          Last frame
        </h2>
        <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Identity</TableHead>
                <TableHead>Detection</TableHead>
                <TableHead>Similarity</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Recorded</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {faces.map((face, index) => (
                <TableRow key={`${index}-${face.bbox.join(",")}`}>
                  <TableCell className="font-medium text-[12.5px] text-[var(--ink)]">
                    {face.student_id ? nameFor(face.student_id) : "—"}
                  </TableCell>
                  <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)] tabular-nums">
                    {(face.detection_score * 100).toFixed(1)}%
                  </TableCell>
                  <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)] tabular-nums">
                    {face.similarity !== null ? `${(face.similarity * 100).toFixed(1)}%` : "—"}
                  </TableCell>
                  <TableCell className="text-[11.5px] text-[var(--ink-muted)]">{face.reason}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        face.state === "MATCH"
                          ? "present"
                          : face.state === "HUMAN_REVIEW"
                            ? "late"
                            : "unknown"
                      }
                    >
                      {face.attendance_recorded ? "BUFFERED" : face.state}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
