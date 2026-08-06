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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface WebcamViewportProps {
  isCameraActive: boolean;
  permissionStatus: "granted" | "prompt" | "denied";
  resolution: string;
  fps: number;
  selectedDevice: string;
  isFullscreen?: boolean;
  containerRef?: React.RefObject<HTMLDivElement | null>;
  videoRef?: React.RefObject<HTMLVideoElement | null>;
  onStartCamera: () => void;
  onStopCamera: () => void;
  onCapture?: () => void;
  onSwitchCamera?: () => void;
  onToggleFullscreen?: () => void;
  children?: React.ReactNode;
}

export function WebcamViewportPlaceholder({
  isCameraActive,
  permissionStatus,
  resolution,
  fps,
  selectedDevice,
  isFullscreen,
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
    <div className="flex flex-col space-y-2 w-full font-mono">
      {/* Viewport Box */}
      <div
        ref={containerRef}
        className={cn(
          "relative w-full aspect-video rounded-md overflow-hidden border border-zinc-800 bg-zinc-950 flex flex-col justify-between select-none camera-grid-bg transition-all",
          isFullscreen && "fixed inset-0 z-50 rounded-none h-screen w-screen"
        )}
      >
        {/* Top Viewport Header */}
        <div className="z-20 p-2.5 flex items-center justify-between bg-zinc-950/90 border-b border-zinc-800/80 text-[11px] text-zinc-300">
          <div className="flex items-center space-x-2">
            <span className={cn("h-1.5 w-1.5 rounded-full", isCameraActive ? "bg-zinc-100" : "bg-zinc-600")} />
            <span className="font-semibold uppercase">{isCameraActive ? "STREAM ACTIVE" : "OFFLINE"}</span>
            <span className="text-zinc-700">|</span>
            <span className="text-zinc-400 hidden sm:inline">{selectedDevice}</span>
          </div>

          <div className="flex items-center space-x-1.5">
            <Badge variant="outline" className="text-[10px] bg-zinc-900 text-zinc-300 border-zinc-800">
              {resolution}
            </Badge>
            <Badge variant="outline" className="text-[10px] bg-zinc-900 text-zinc-300 border-zinc-800">
              {isCameraActive ? `${fps} FPS` : "0 FPS"}
            </Badge>
          </div>
        </div>

        {/* Video Element */}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={cn("absolute inset-0 w-full h-full object-cover z-0", !isCameraActive && "hidden")}
        />

        {/* Offline Placeholder */}
        {!isCameraActive && (
          <div className="z-10 absolute inset-0 flex flex-col items-center justify-center space-y-2 p-6 text-center">
            <div className="h-10 w-10 rounded bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400">
              <CameraOff className="h-4 w-4" />
            </div>
            <p className="text-xs text-zinc-400">
              Click "Start Stream" to initialize camera feed
            </p>
          </div>
        )}

        {/* Bounding Box Overlays */}
        {isCameraActive && children && (
          <div className="absolute inset-0 z-10 pointer-events-none">{children}</div>
        )}

        {/* Viewport Footer Bar */}
        <div className="z-20 p-2 flex items-center justify-between bg-zinc-950/90 border-t border-zinc-800/80 text-[10px] text-zinc-400">
          <span>STATUS: {permissionStatus.toUpperCase()}</span>
          <span>OPENCV / WEBRTC READY</span>
        </div>
      </div>

      {/* Control Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-2 bg-zinc-900 p-2 rounded border border-zinc-800 text-xs">
        <div className="flex items-center space-x-2">
          {!isCameraActive ? (
            <Button size="sm" variant="default" onClick={onStartCamera} className="space-x-1">
              <Play className="h-3 w-3 fill-current" />
              <span>Start Stream</span>
            </Button>
          ) : (
            <Button size="sm" variant="danger" onClick={onStopCamera} className="space-x-1">
              <Square className="h-3 w-3 fill-current" />
              <span>Stop Stream</span>
            </Button>
          )}

          {onCapture && (
            <Button size="sm" variant="secondary" onClick={onCapture} disabled={!isCameraActive} className="space-x-1">
              <Camera className="h-3 w-3" />
              <span>Snapshot</span>
            </Button>
          )}

          {onSwitchCamera && (
            <Button size="sm" variant="outline" onClick={onSwitchCamera} disabled={!isCameraActive} className="space-x-1">
              <RefreshCw className="h-3 w-3" />
              <span className="hidden sm:inline">Switch Device</span>
            </Button>
          )}
        </div>

        {onToggleFullscreen && (
          <Button size="sm" variant="ghost" onClick={onToggleFullscreen} className="space-x-1 text-zinc-400">
            {isFullscreen ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
            <span className="hidden sm:inline">{isFullscreen ? "Exit" : "Fullscreen"}</span>
          </Button>
        )}
      </div>
    </div>
  );
}
