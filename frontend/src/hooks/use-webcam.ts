"use client";

import { useState, useRef, useCallback, useEffect, type RefObject } from "react";

type PermissionStatus = "granted" | "prompt" | "denied";

/**
 * Drives a camera stream into refs the caller owns.
 *
 * The refs are arguments rather than return values so the hook hands back plain
 * state, which components can read during render.
 */
export function useWebcam(
  videoRef: RefObject<HTMLVideoElement | null>,
  containerRef: RefObject<HTMLDivElement | null>
) {
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [permissionStatus, setPermissionStatus] = useState<PermissionStatus>("prompt");
  const [resolution, setResolutionLabel] = useState("—");
  const [fps, setFps] = useState(0);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const [selectedDeviceLabel, setSelectedDeviceLabel] = useState("No camera selected");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const fpsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const frameCountRef = useRef(0);

  // Enumerate cameras on mount
  useEffect(() => {
    navigator.mediaDevices?.enumerateDevices().then((devs) => {
      const cams = devs.filter((d) => d.kind === "videoinput");
      setDevices(cams);
      if (cams.length > 0) {
        setSelectedDeviceId((current) => current || cams[0].deviceId);
        setSelectedDeviceLabel((current) =>
          current === "No camera selected" ? cams[0].label || "Camera 1" : current
        );
      }
    }).catch(() => {});
  }, []);

  // Listen for fullscreen change
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  const startCamera = useCallback(async (deviceId?: string) => {
    setError(null);
    const targetId = deviceId ?? selectedDeviceId;

    const constraints: MediaStreamConstraints = {
      video: targetId
        ? { deviceId: { exact: targetId }, width: { ideal: 1280 }, height: { ideal: 720 } }
        : { width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    };

    try {
      // Stop any existing stream first
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;

      const video = videoRef.current;
      if (video) {
        video.srcObject = stream;
        await video.play().catch(() => {});
      }

      // Read actual resolution from track settings
      const track = stream.getVideoTracks()[0];
      const settings = track.getSettings();
      const w = settings.width ?? 1280;
      const h = settings.height ?? 720;
      setResolutionLabel(`${w}×${h}`);
      setSelectedDeviceLabel(track.label || "Camera");

      // Re-enumerate to get labels (they appear after permission is granted)
      navigator.mediaDevices.enumerateDevices().then((devs) => {
        const cams = devs.filter((d) => d.kind === "videoinput");
        setDevices(cams);
      });

      setIsCameraActive(true);
      setPermissionStatus("granted");

      // FPS counter
      if (fpsIntervalRef.current) clearInterval(fpsIntervalRef.current);
      frameCountRef.current = 0;
      fpsIntervalRef.current = setInterval(() => {
        setFps(frameCountRef.current);
        frameCountRef.current = 0;
      }, 1000);

      // Count frames via requestAnimationFrame
      const countFrame = () => {
        if (streamRef.current?.active) {
          frameCountRef.current++;
          requestAnimationFrame(countFrame);
        }
      };
      requestAnimationFrame(countFrame);

    } catch (err: unknown) {
      const e = err as Error;
      if (e.name === "NotAllowedError" || e.name === "PermissionDeniedError") {
        setPermissionStatus("denied");
        setError("Camera permission denied. Please allow access in your browser settings.");
      } else if (e.name === "NotFoundError") {
        setError("No camera device found.");
      } else {
        setError(`Camera error: ${e.message}`);
      }
      setIsCameraActive(false);
    }
  }, [selectedDeviceId, videoRef]);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    const video = videoRef.current;
    if (video) {
      video.srcObject = null;
    }
    if (fpsIntervalRef.current) {
      clearInterval(fpsIntervalRef.current);
    }
    setIsCameraActive(false);
    setFps(0);
    setResolutionLabel("—");
  }, [videoRef]);

  const switchCamera = useCallback((deviceId: string) => {
    const dev = devices.find((d) => d.deviceId === deviceId);
    setSelectedDeviceId(deviceId);
    setSelectedDeviceLabel(dev?.label || "Camera");
    if (isCameraActive) {
      startCamera(deviceId);
    }
  }, [devices, isCameraActive, startCamera]);

  // Capture a frame from the video element to a canvas, return a data URL
  const captureFrame = useCallback((): string | null => {
    const video = videoRef.current;
    if (!video || !isCameraActive) return null;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    return canvas.toDataURL("image/png");
  }, [isCameraActive, videoRef]);

  const toggleFullscreen = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    if (!document.fullscreenElement) {
      container.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }, [containerRef]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (fpsIntervalRef.current) {
        clearInterval(fpsIntervalRef.current);
      }
    };
  }, []);

  return {
    isCameraActive,
    permissionStatus,
    resolution,
    fps,
    devices,
    selectedDeviceId,
    selectedDeviceLabel,
    isFullscreen,
    error,
    startCamera: () => startCamera(),
    stopCamera,
    switchCamera,
    captureFrame,
    toggleFullscreen,
  };
}
