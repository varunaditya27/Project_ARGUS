"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Play, Square } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorNotice } from "@/components/common/async-state";
import { CctvViewport } from "@/components/cctv/cctv-viewport";
import { LiveRecognitionOverlay } from "@/components/webcam/live-recognition-overlay";
import { cameraService } from "@/services/camera";
import { recognitionService } from "@/services/recognition";
import { sessionService } from "@/services/session";
import { studentService } from "@/services/student";
import type { FaceDecision } from "@/types";

/** Same cadence as /live-recognition - one frame in flight at a time. */
const FRAME_INTERVAL_MS = 700;

export default function CctvPage() {
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [cameraId, setCameraId] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const [sessionId, setSessionId] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [faces, setFaces] = useState<FaceDecision[]>([]);
  const [frameSize, setFrameSize] = useState({ width: 0, height: 0 });
  const [latency, setLatency] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const frameNumber = useRef(0);
  const running = useRef(false);

  const cameras = useQuery({ queryKey: ["cameras"], queryFn: () => cameraService.listCameras() });
  const models = useQuery({ queryKey: ["models"], queryFn: () => recognitionService.models() });
  const sessions = useQuery({
    queryKey: ["sessions", "ACTIVE"],
    queryFn: () => sessionService.listSessions({ status: "ACTIVE", limit: 50 }),
  });

  // Falls back to the first configured camera until the user picks one explicitly.
  const selectedCameraId = cameraId || cameras.data?.[0]?.camera_id || "";

  // A new camera means a new MJPEG connection - drop the old "connected" state for it.
  // Adjusted during render (React's documented pattern for resetting state when a prop
  // changes) rather than in an effect, so it can't cause an extra render pass.
  const previousCameraId = useRef(selectedCameraId);
  if (previousCameraId.current !== selectedCameraId) {
    previousCameraId.current = selectedCameraId;
    setIsConnected(false);
    setStreamError(null);
    setIsRunning(false);
  }

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

  // Same loop as /live-recognition, except the frame source is the MJPEG <img> the
  // camera proxy keeps refreshing, not a getUserMedia <video>.
  useEffect(() => {
    if (!isRunning) return;
    running.current = true;
    let timer: ReturnType<typeof setTimeout>;

    const grabFrame = async (): Promise<Blob | null> => {
      const img = imgRef.current;
      if (!img?.naturalWidth) return null;
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext("2d")?.drawImage(img, 0, 0);
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
              `cctv-${selectedCameraId}-${frameNumber.current.toString().padStart(6, "0")}`
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
  }, [isRunning, sessionId, selectedCameraId]);

  const streamUrl = selectedCameraId ? cameraService.mjpegUrl(selectedCameraId) : null;
  const selectedLabel = cameras.data?.find((c) => c.camera_id === selectedCameraId)?.label ?? "";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">
            CCTV Cameras
          </h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
            {latency !== null ? `Round trip: ${latency} ms · ` : ""}
            {faces.length} face{faces.length === 1 ? "" : "s"} in the last frame
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={selectedCameraId}
            onChange={(event) => setCameraId(event.target.value)}
            className="w-56"
          >
            {cameras.data?.length === 0 ? <option value="">No cameras configured</option> : null}
            {cameras.data?.map((camera) => (
              <option key={camera.camera_id} value={camera.camera_id}>
                {camera.label}
              </option>
            ))}
          </Select>
          <Select
            value={sessionId}
            onChange={(event) => setSessionId(event.target.value)}
            className="w-72"
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
      </div>

      {cameras.data?.length === 0 ? (
        <div className="rounded-xl border border-[#DDCBA0] bg-[var(--status-late-bg)] px-4 py-3 flex items-start gap-2.5">
          <AlertTriangle className="h-4 w-4 text-[var(--status-late)] shrink-0 mt-0.5" />
          <p className="text-[12px] text-[var(--ink-muted)]">
            No campus cameras are configured. Set ARGUS_CAMERA_STEPS_RTSP_URL and/or
            ARGUS_CAMERA_WALL_RTSP_URL in the backend&apos;s .env and restart it.
          </p>
        </div>
      ) : null}

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

      <CctvViewport
        cameraLabel={selectedLabel}
        streamUrl={streamUrl}
        isConnected={isConnected}
        error={streamError}
        imgRef={imgRef}
        onLoad={() => {
          setIsConnected(true);
          setStreamError(null);
        }}
        onError={() => {
          setIsConnected(false);
          setStreamError(
            "Couldn't reach the camera proxy. The camera is only visible on the campus LAN - " +
              "check the backend can reach it, and that its RTSP path is correct."
          );
        }}
      >
        {isRunning ? (
          <LiveRecognitionOverlay
            faces={faces}
            frameWidth={frameSize.width}
            frameHeight={frameSize.height}
            labelFor={(face) => (face.student_id ? nameFor(face.student_id) : face.state)}
          />
        ) : null}
      </CctvViewport>

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
            disabled={!isConnected}
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
