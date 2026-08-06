import { simulateDelay } from "./api";
import { MOCK_ACTIVE_OVERLAYS, MOCK_LIVE_METRICS } from "@/mock/recognition-mock";
import { BoundingBox, LiveMetrics } from "@/types";

export const recognitionService = {
  async getLiveMetrics(): Promise<LiveMetrics> {
    return simulateDelay(MOCK_LIVE_METRICS, 150);
  },

  async getActiveDetections(): Promise<BoundingBox[]> {
    return simulateDelay(MOCK_ACTIVE_OVERLAYS, 150);
  },

  async startStream(): Promise<{ success: boolean; message: string }> {
    return simulateDelay({ success: true, message: "Detection engine activated." }, 300);
  },

  async stopStream(): Promise<{ success: boolean; message: string }> {
    return simulateDelay({ success: true, message: "Detection engine paused." }, 200);
  },
};
