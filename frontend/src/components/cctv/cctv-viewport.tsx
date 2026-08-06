"use client";

import React from "react";
import { AlertCircle, VideoOff } from "lucide-react";
import { cn } from "@/lib/utils";

interface CctvViewportProps {
  cameraLabel: string;
  streamUrl: string | null;
  isConnected: boolean;
  error: string | null;
  imgRef: React.RefObject<HTMLImageElement | null>;
  onLoad: () => void;
  onError: () => void;
  children?: React.ReactNode;
}

/** Same visual language as WebcamViewport, but the video source is the backend's MJPEG
 * proxy (an <img> that keeps replacing its own bytes) instead of getUserMedia - there is
 * no "start/stop" here, the feed is live the moment a camera is selected. */
export function CctvViewport({
  cameraLabel,
  streamUrl,
  isConnected,
  error,
  imgRef,
  onLoad,
  onError,
  children,
}: CctvViewportProps) {
  return (
    <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-[#0A0C10] border border-[#1E2330] flex flex-col justify-between select-none">
      <div className="z-20 px-3 py-2 flex items-center justify-between bg-black/60 backdrop-blur-sm border-b border-white/5">
        <div className="flex items-center gap-2 text-[11px] text-white/70">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full shrink-0",
              isConnected ? "bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.8)]" : "bg-white/20"
            )}
          />
          <span className="font-semibold uppercase tracking-wide text-white/90">
            {isConnected ? "Live" : "Connecting"}
          </span>
          <span className="text-white/30">·</span>
          <span className="truncate max-w-[180px] text-white/50">{cameraLabel}</span>
        </div>
        <span className="text-[10px] font-mono text-white/40 bg-white/5 px-1.5 py-0.5 rounded">
          CCTV
        </span>
      </div>

      {streamUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- MJPEG multipart stream, not a static asset Next can optimise
        <img
          ref={imgRef}
          src={streamUrl}
          alt={`${cameraLabel} live feed`}
          crossOrigin="anonymous"
          onLoad={onLoad}
          onError={onError}
          className={cn("absolute inset-0 w-full h-full object-cover z-0", !isConnected && "hidden")}
        />
      ) : null}

      {!isConnected && (
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
                <VideoOff className="h-5 w-5 text-white/30" />
              </div>
              <p className="text-[12px] text-white/30">
                {streamUrl ? "Connecting to camera..." : "Select a camera"}
              </p>
            </>
          )}
        </div>
      )}

      {isConnected && children ? (
        <div className="absolute inset-0 z-10 pointer-events-none">{children}</div>
      ) : null}

      <div className="z-20 px-3 py-1.5 flex items-center justify-between bg-black/60 backdrop-blur-sm border-t border-white/5">
        <span className="text-[10px] font-mono text-white/25 uppercase tracking-widest">
          RTSP proxy · MJPEG
        </span>
      </div>
    </div>
  );
}
