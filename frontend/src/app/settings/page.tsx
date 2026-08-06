"use client";

import React, { useState } from "react";
import { Save, Database, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { DEFAULT_MODEL_SETTINGS } from "@/mock/reports-mock";

export default function SettingsPage() {
  const [similarityCutoff, setSimilarityCutoff] = useState<number>(
    DEFAULT_MODEL_SETTINGS.similarityThreshold * 100
  );
  const [maskVariants, setMaskVariants] = useState<number>(
    DEFAULT_MODEL_SETTINGS.maskSynthesisVariants
  );
  const [unknownCutoff, setUnknownCutoff] = useState<number>(
    DEFAULT_MODEL_SETTINGS.unknownRejectionThreshold * 100
  );
  const [isSaved, setIsSaved] = useState(false);

  const handleSave = () => {
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2500);
  };

  return (
    <div className="space-y-7">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Settings</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">Model configuration and system status</p>
        </div>
        <Button onClick={handleSave} variant="primary" size="sm">
          <Save className="h-3.5 w-3.5 mr-1.5" />
          {isSaved ? "Saved" : "Save Changes"}
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Model Configuration */}
        <div className="lg:col-span-7 space-y-5">
          <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
            <div className="px-5 py-4 border-b border-[var(--stone-100)]">
              <h2 className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
                Model Hyperparameters
              </h2>
            </div>
            <div className="px-5 py-5 space-y-5">

              <div className="space-y-1.5">
                <label className="text-[12px] font-semibold text-[var(--ink)]">
                  Face Detection Backbone
                </label>
                <Select defaultValue="SCRFD-10G">
                  <option value="SCRFD-10G">SCRFD-10G (InsightFace)</option>
                  <option value="RetinaFace-ResNet50">RetinaFace-ResNet50</option>
                  <option value="MTCNN-Fast">MTCNN</option>
                </Select>
              </div>

              <div className="space-y-1.5">
                <label className="text-[12px] font-semibold text-[var(--ink)]">
                  Feature Vector Backbone
                </label>
                <Select defaultValue="ArcFace-R100">
                  <option value="ArcFace-R100">ArcFace-ResNet100</option>
                  <option value="CosFace-R50">CosFace-ResNet50</option>
                  <option value="MobileFaceNet">MobileFaceNet</option>
                </Select>
              </div>

              <div className="space-y-3 pt-1">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[12px] font-semibold text-[var(--ink)]">Cosine Similarity Cutoff</p>
                    <p className="text-[11px] text-[var(--ink-faint)]">Minimum score for a match to be accepted</p>
                  </div>
                  <span className="text-[15px] font-bold text-[var(--accent)] tabular-nums">
                    {(similarityCutoff / 100).toFixed(2)}
                  </span>
                </div>
                <Slider
                  value={[similarityCutoff]}
                  onValueChange={(val) => setSimilarityCutoff(val[0])}
                  min={50} max={95} step={1}
                />
              </div>

              <div className="space-y-3 pt-1">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[12px] font-semibold text-[var(--ink)]">Synthetic Mask Variants</p>
                    <p className="text-[11px] text-[var(--ink-faint)]">Number of mask augmentations per student</p>
                  </div>
                  <span className="text-[15px] font-bold text-[var(--accent)] tabular-nums">
                    {maskVariants}
                  </span>
                </div>
                <Slider
                  value={[maskVariants]}
                  onValueChange={(val) => setMaskVariants(val[0])}
                  min={5} max={30} step={1}
                />
              </div>

              <div className="space-y-3 pt-1">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[12px] font-semibold text-[var(--ink)]">Unknown Rejection Threshold</p>
                    <p className="text-[11px] text-[var(--ink-faint)]">Below this score, face is flagged as unknown</p>
                  </div>
                  <span className="text-[15px] font-bold text-[var(--accent)] tabular-nums">
                    {(unknownCutoff / 100).toFixed(2)}
                  </span>
                </div>
                <Slider
                  value={[unknownCutoff]}
                  onValueChange={(val) => setUnknownCutoff(val[0])}
                  min={20} max={60} step={1}
                />
              </div>

            </div>
          </div>
        </div>

        {/* System Status */}
        <div className="lg:col-span-5 space-y-5">
          <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
            <div className="px-5 py-4 border-b border-[var(--stone-100)]">
              <h2 className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
                System Status
              </h2>
            </div>
            <div className="divide-y divide-[var(--stone-100)]">
              <div className="px-5 py-3.5 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="h-7 w-7 rounded-md bg-[var(--status-present-bg)] flex items-center justify-center">
                    <Database className="h-3.5 w-3.5 text-[var(--status-present)]" />
                  </div>
                  <div>
                    <p className="text-[12px] font-medium text-[var(--ink)]">ChromaDB Vector Store</p>
                    <p className="text-[10.5px] text-[var(--ink-faint)]">320 collections</p>
                  </div>
                </div>
                <Badge variant="present">Online</Badge>
              </div>

              <div className="px-5 py-3.5 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="h-7 w-7 rounded-md bg-[var(--status-present-bg)] flex items-center justify-center">
                    <Database className="h-3.5 w-3.5 text-[var(--status-present)]" />
                  </div>
                  <div>
                    <p className="text-[12px] font-medium text-[var(--ink)]">PostgreSQL Database</p>
                    <p className="text-[10.5px] text-[var(--ink-faint)]">Primary connection</p>
                  </div>
                </div>
                <Badge variant="present">Connected</Badge>
              </div>

              <div className="px-5 py-3.5 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="h-7 w-7 rounded-md bg-[var(--accent-light)] flex items-center justify-center">
                    <Cpu className="h-3.5 w-3.5 text-[var(--accent)]" />
                  </div>
                  <div>
                    <p className="text-[12px] font-medium text-[var(--ink)]">GPU Acceleration</p>
                    <p className="text-[10.5px] text-[var(--ink-faint)]">CUDA 12.2</p>
                  </div>
                </div>
                <Badge variant="default">Active</Badge>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
