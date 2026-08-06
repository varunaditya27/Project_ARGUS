"use client";

import React from "react";
import type { FaceDecision } from "@/types";

const TONE: Record<FaceDecision["state"], string> = {
  MATCH: "border-emerald-400 bg-emerald-400/10",
  HUMAN_REVIEW: "border-amber-400 bg-amber-400/10",
  UNKNOWN: "border-zinc-300 bg-zinc-100/10",
};

/** Draws the backend's boxes over the video, scaled from frame pixels to percent. */
export function LiveRecognitionOverlay({
  faces,
  frameWidth,
  frameHeight,
  labelFor,
}: {
  faces: FaceDecision[];
  frameWidth: number;
  frameHeight: number;
  labelFor: (face: FaceDecision) => string;
}) {
  if (!frameWidth || !frameHeight) return null;
  return (
    <div className="relative w-full h-full font-mono">
      {faces.map((face, index) => {
        const [x1, y1, x2, y2] = face.bbox;
        return (
          <div
            key={`${index}-${x1}-${y1}`}
            className={`absolute border rounded-xs transition-all ${TONE[face.state]}`}
            style={{
              left: `${(x1 / frameWidth) * 100}%`,
              top: `${(y1 / frameHeight) * 100}%`,
              width: `${((x2 - x1) / frameWidth) * 100}%`,
              height: `${((y2 - y1) / frameHeight) * 100}%`,
            }}
          >
            <div className="absolute -top-5 left-0 flex items-center gap-1 bg-zinc-900 text-white px-1.5 rounded-xs text-[10px] font-semibold whitespace-nowrap border border-zinc-700">
              <span>{labelFor(face)}</span>
              {face.similarity !== null ? (
                <span className="opacity-75">{(face.similarity * 100).toFixed(0)}%</span>
              ) : null}
            </div>
            <div className="absolute -bottom-4 left-0 text-[9px] text-zinc-200 bg-zinc-950/90 px-1 rounded-xs">
              {face.state}
            </div>
          </div>
        );
      })}
    </div>
  );
}
