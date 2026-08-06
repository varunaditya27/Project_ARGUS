import { api } from "./api";
import type { FrameResult, HealthResponse, ModelsResponse } from "@/types";

interface OfflineRunResult {
  session_id: string | null;
  processed: number;
  skipped: number;
  faces_detected: number;
  matched: number;
  human_review: number;
  unknown: number;
  attendance_observations: number;
}

function upload(field: string, file: Blob, filename: string, sessionId?: string) {
  const form = new FormData();
  form.append(field, file, filename);
  if (sessionId) form.append("session_id", sessionId);
  return form;
}

export const recognitionService = {
  /** One frame. With a session_id, a MATCH is buffered as attendance. */
  recognizeFrame(frame: Blob, sessionId?: string, frameId?: string) {
    const form = upload("frame", frame, "frame.jpg", sessionId);
    if (frameId) form.append("frame_id", frameId);
    return api.postForm<FrameResult>("/recognize", form);
  },

  recognizeVideo(video: File, sessionId?: string) {
    return api.postForm<OfflineRunResult>(
      "/recognize/video",
      upload("video", video, video.name, sessionId)
    );
  },

  recognizeBatch(archive: File, sessionId?: string) {
    return api.postForm<OfflineRunResult>(
      "/recognize/batch",
      upload("archive", archive, archive.name, sessionId)
    );
  },

  /** Which vision components are wired, and whether thresholds are calibrated. */
  models() {
    return api.get<ModelsResponse>("/models");
  },

  /** Answers 503 while a dependency is down; the body still lists the probes. */
  health() {
    return api.get<HealthResponse>("/health", [503]);
  },
};

export type { OfflineRunResult };
