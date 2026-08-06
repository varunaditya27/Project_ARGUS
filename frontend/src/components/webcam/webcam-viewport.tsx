"use client";

import React from "react";
import {
  Camera,
  CameraOff,
  RefreshCw,
  Maximize2,
  Minimize2,
  Play,
  Square,
  AlertCircle,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface WebcamViewportProps {
  isCameraActive: boolean;
  permissionStatus: "granted" | "prompt" | "denied";
  resolution: string;
  fps: number;
  devices: MediaDeviceInfo[];
  selectedDeviceId: string;
  selectedDeviceLabel: string;
  isFullscreen?: boolean;
  error?: string | null;
  containerRef?: React.RefObject<HTMLDivElement | null>;
  videoRef?: React.RefObject<HTMLVideoElement | null>;
  onStartCamera: () => void;
  onStopCamera: () => void;
  onCapture?: () => void;
  onSwitchCamera?: (deviceId: string) => void;
  onToggleFullscreen?: () => void;
  children?: React.ReactNode;
}

export function WebcamViewport({
  isCameraActive,
  permissionStatus,
  resolution,
  fps,
  devices,
  selectedDeviceId,
  selectedDeviceLabel,
  isFullscreen,
  error,
  containerRef,
  videoRef,
  onStartCamera,
  onStopCamera,
  onCapture,
  onSwitchCamera,
  onToggleFullscreen,
  children,
}: WebcamViewportProps) {
  return (
    <div className="flex flex-col gap-2 w-full">
      {/* Viewport */}
      <div
        ref={containerRef}
        className={cn(
          "relative w-full aspect-video rounded-xl overflow-hidden bg-[#0A0C10] border border-[#1E2330] flex flex-col justify-between select-none",
          isFullscreen && "fixed inset-0 z-50 rounded-none aspect-auto h-screen w-screen"
        )}
      >
        {/* Header bar */}
        <div className="z-20 px-3 py-2 flex items-center justify-between bg-black/60 backdrop-blur-sm border-b border-white/5">
          <div className="flex items-center gap-2 text-[11px] text-white/70">
            <span className={cn(
              "h-1.5 w-1.5 rounded-full shrink-0",
              isCameraActive ? "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.8)]" : "bg-white/20"
            )} />
            <span className="font-semibold uppercase tracking-wide text-white/90">
              {isCameraActive ? "Live" : "Offline"}
            </span>
            <span className="text-white/30">·</span>
            <span className="truncate max-w-[180px] text-white/50">{selectedDeviceLabel}</span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-white/40">
            {isCameraActive && (
              <>
                <span className="bg-white/5 px-1.5 py-0.5 rounded">{resolution}</span>
                <span className="bg-white/5 px-1.5 py-0.5 rounded">{fps} fps</span>
              </>
            )}
          </div>
        </div>

        {/* Video element — always in DOM so ref is attached */}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={cn(
            "absolute inset-0 w-full h-full object-cover z-0",
            !isCameraActive && "hidden"
          )}
        />

        {/* Offline / error state */}
        {!isCameraActive && (
          <div className="z-10 absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
            {error ? (
              <>
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-950/60 border border-red-800/40">
                  <AlertCircle className="h-5 w-5 text-red-400" />
                </div>
                <p className="text-[12px] text-red-300 max-w-xs leading-relaxed">{error}</p>
              </>
            ) : (
              <>
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white/5 border border-white/10">
                  <CameraOff className="h-5 w-5 text-white/30" />
                </div>
                <p className="text-[12px] text-white/30">
                  {permissionStatus === "denied"
                    ? "Camera access denied"
                    : "Press Start to open camera"}
                </p>
              </>
            )}
          </div>
        )}

        {/* Overlay slot (bounding boxes etc.) */}
        {isCameraActive && children && (
          <div className="absolute inset-0 z-10 pointer-events-none">{children}</div>
        )}

        {/* Footer bar */}
        <div className="z-20 px-3 py-1.5 flex items-center justify-between bg-black/60 backdrop-blur-sm border-t border-white/5">
          <span className="text-[10px] font-mono text-white/25 uppercase tracking-widest">
            {permissionStatus === "granted" ? "WebRTC · Permission Granted" : permissionStatus === "denied" ? "Permission Denied" : "Awaiting Permission"}
          </span>
          {onToggleFullscreen && (
            <button
              onClick={onToggleFullscreen}
              className="text-white/30 hover:text-white/70 transition-colors p-0.5"
              title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            >
              {isFullscreen
                ? <Minimize2 className="h-3.5 w-3.5" />
                : <Maximize2 className="h-3.5 w-3.5" />}
            </button>
          )}
        </div>
      </div>

      {/* Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-lg border border-[var(--stone-200)] bg-white">
        <div className="flex items-center gap-2">
          {!isCameraActive ? (
            <Button size="sm" variant="default" onClick={onStartCamera}>
              <Play className="h-3.5 w-3.5 mr-1.5 fill-current" />
              Start Camera
            </Button>
          ) : (
            <Button size="sm" variant="danger" onClick={onStopCamera}>
              <Square className="h-3.5 w-3.5 mr-1.5 fill-current" />
              Stop
            </Button>
          )}

          {onCapture && (
            <Button size="sm" variant="secondary" onClick={onCapture} disabled={!isCameraActive}>
              <Camera className="h-3.5 w-3.5 mr-1.5" />
              Snapshot
            </Button>
          )}
        </div>

        {/* Camera selector */}
        {devices.length > 1 && onSwitchCamera && (
          <div className="relative">
            <select
              value={selectedDeviceId}
              onChange={(e) => onSwitchCamera(e.target.value)}
              className="h-7 pl-2.5 pr-7 text-[11.5px] border border-[var(--stone-300)] rounded-md bg-white text-[var(--ink)] appearance-none focus:outline-none focus:border-[var(--accent)] cursor-pointer"
            >
              {devices.map((d, i) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label || `Camera ${i + 1}`}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1.5 h-3.5 w-3.5 text-[var(--ink-faint)] pointer-events-none" />
          </div>
        )}

        {devices.length <= 1 && (
          <div className="flex items-center gap-1.5 text-[11px] text-[var(--ink-faint)]">
            <RefreshCw className="h-3 w-3" />
            <span>{selectedDeviceLabel || "Default camera"}</span>
          </div>
        )}
      </div>
    </div>
  );
}
