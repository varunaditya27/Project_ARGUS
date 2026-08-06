import { BoundingBox, LiveMetrics } from "@/types";

export const MOCK_LIVE_METRICS: LiveMetrics = {
  fps: 30,
  latencyMs: 14,
  activeDetections: 3,
  systemStatus: "ACTIVE",
  gpuUsage: 18.4,
  cpuUsage: 12.1,
};

export const MOCK_ACTIVE_OVERLAYS: BoundingBox[] = [
  {
    id: "box_1",
    label: "Nidhi Mahesh",
    confidence: 0.962,
    status: "PRESENT",
    isMasked: true,
    x: 20,
    y: 28,
    width: 26,
    height: 52,
  },
  {
    id: "box_2",
    label: "Unknown Subject",
    confidence: 0.410,
    status: "UNKNOWN",
    isMasked: true,
    x: 48,
    y: 24,
    width: 24,
    height: 50,
  },
  {
    id: "box_3",
    label: "Varun Aditya",
    confidence: 0.956,
    status: "PRESENT",
    isMasked: true,
    x: 70,
    y: 29,
    width: 25,
    height: 51,
  },
];
