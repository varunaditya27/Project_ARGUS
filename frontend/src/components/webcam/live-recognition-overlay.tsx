"use client";

import React from "react";
import { BoundingBox } from "@/types";
import { cn } from "@/lib/utils";

interface LiveRecognitionOverlayProps {
  overlays: BoundingBox[];
}

export function LiveRecognitionOverlay({ overlays }: LiveRecognitionOverlayProps) {
  return (
    <div className="relative w-full h-full font-mono">
      {overlays.map((box) => {
        return (
          <div
            key={box.id}
            className="absolute border border-zinc-200 bg-zinc-100/10 dark:border-zinc-300 dark:bg-zinc-100/5 rounded-xs transition-all pointer-events-auto flex flex-col justify-between p-1"
            style={{
              left: `${box.x}%`,
              top: `${box.y}%`,
              width: `${box.width}%`,
              height: `${box.height}%`,
            }}
          >
            {/* Label Tag */}
            <div className="absolute -top-5 left-0 flex items-center space-x-1 bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 px-1.5 py-0.2 rounded-xs text-[10px] font-semibold whitespace-nowrap select-none border border-zinc-700">
              <span>{box.label}</span>
              <span className="opacity-75">{(box.confidence * 100).toFixed(0)}%</span>
            </div>

            {/* Occlusion Tag */}
            <div className="mt-auto flex items-center justify-between text-[9px] text-zinc-300 bg-zinc-950/90 px-1 py-0.2 rounded-xs">
              <span>{box.isMasked ? "MASKED" : "UNMASKED"}</span>
              <span className="font-bold">{box.status}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
