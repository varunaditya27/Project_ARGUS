import { API_BASE_URL, api } from "./api";
import type { Camera } from "@/types";

export const cameraService = {
  /** Configured campus CCTV cameras; empty until ARGUS_CAMERA_*_RTSP_URL is set. */
  listCameras() {
    return api.get<Camera[]>("/cameras");
  },

  /** MJPEG proxy - safe to point an <img> at directly, never carries credentials. */
  mjpegUrl(cameraId: string) {
    return `${API_BASE_URL}/cameras/${cameraId}/mjpeg`;
  },
};
