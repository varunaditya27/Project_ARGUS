import { create } from "zustand";
import { BoundingBox, LiveMetrics } from "@/types";
import { MOCK_ACTIVE_OVERLAYS, MOCK_LIVE_METRICS } from "@/mock/recognition-mock";

interface LiveRecognitionState {
  isDetecting: boolean;
  isPaused: boolean;
  metrics: LiveMetrics;
  overlays: BoundingBox[];
  selectedCamera: string;
  startDetection: () => void;
  stopDetection: () => void;
  pauseDetection: () => void;
  resumeDetection: () => void;
  clearResults: () => void;
  setSelectedCamera: (camId: string) => void;
}

export const useLiveRecognitionStore = create<LiveRecognitionState>((set) => ({
  isDetecting: true,
  isPaused: false,
  metrics: MOCK_LIVE_METRICS,
  overlays: MOCK_ACTIVE_OVERLAYS,
  selectedCamera: "CAM_HD_101",
  startDetection: () => set({ isDetecting: true, isPaused: false }),
  stopDetection: () => set({ isDetecting: false, isPaused: false }),
  pauseDetection: () => set({ isPaused: true }),
  resumeDetection: () => set({ isPaused: false }),
  clearResults: () => set({ overlays: [] }),
  setSelectedCamera: (camId) => set({ selectedCamera: camId }),
}));
