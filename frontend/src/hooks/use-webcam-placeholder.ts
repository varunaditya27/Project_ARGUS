import { useState, useRef, useCallback } from "react";

export function useWebcamPlaceholder() {
  const [isCameraActive, setIsCameraActive] = useState<boolean>(true);
  const [permissionStatus, setPermissionStatus] = useState<"granted" | "prompt" | "denied">("granted");
  const [resolution, setResolution] = useState<string>("HD 1280x720");
  const [fps, setFps] = useState<number>(30);
  const [selectedDevice, setSelectedDevice] = useState<string>("Integrated HD Webcam (Default)");
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [lastCapturedAt, setLastCapturedAt] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const devices = [
    "Integrated HD Webcam (Default)",
    "Logitech Brio 4K (External)",
    "Virtual Cam Feed (ARGUS Stream)",
  ];

  const startCamera = useCallback(() => {
    setIsCameraActive(true);
    // Prepared structure for real API connection:
    // navigator.mediaDevices?.getUserMedia({ video: true }).then(...).catch(...)
  }, []);

  const stopCamera = useCallback(() => {
    setIsCameraActive(false);
  }, []);

  const switchCamera = useCallback(() => {
    const currentIndex = devices.indexOf(selectedDevice);
    const nextIndex = (currentIndex + 1) % devices.length;
    setSelectedDevice(devices[nextIndex]);
  }, [selectedDevice, devices]);

  const captureFrame = useCallback(() => {
    const timestamp = new Date().toLocaleTimeString();
    setLastCapturedAt(timestamp);
    return `captured_frame_${Date.now()}.png`;
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  }, []);

  return {
    isCameraActive,
    permissionStatus,
    resolution,
    fps,
    devices,
    selectedDevice,
    isFullscreen,
    lastCapturedAt,
    videoRef,
    containerRef,
    startCamera,
    stopCamera,
    switchCamera,
    captureFrame,
    toggleFullscreen,
    setResolution,
  };
}
