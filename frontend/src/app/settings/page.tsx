"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Cpu, Database } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { AsyncState } from "@/components/common/async-state";
import { API_BASE_URL } from "@/services/api";
import { recognitionService } from "@/services/recognition";

const threshold = (value: number | null) => (value === null ? "not calibrated" : value.toFixed(3));

export default function SettingsPage() {
  const models = useQuery({ queryKey: ["models"], queryFn: () => recognitionService.models() });
  const health = useQuery({ queryKey: ["health"], queryFn: () => recognitionService.health() });

  return (
    <div className="space-y-7">
      <div>
        <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">System</h1>
        <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">
          Read-only. Every value below is set by the backend environment, not from here.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Panel title="Recognition stack" icon={<Cpu className="h-3.5 w-3.5" />}>
          <AsyncState isLoading={models.isLoading} error={models.error} rows={3}>
            <div className="divide-y divide-[var(--stone-100)]">
              {models.data?.components.map((component) => (
                <div key={component.name} className="px-5 py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[12.5px] font-medium text-[var(--ink)]">{component.name}</p>
                    <p className="text-[10.5px] text-[var(--ink-faint)] truncate">{component.detail}</p>
                  </div>
                  <Badge variant={component.configured ? "present" : "unknown"}>
                    {component.configured ? "LOADED" : "MISSING"}
                  </Badge>
                </div>
              ))}
              <div className="px-5 py-3 flex items-center justify-between">
                <p className="text-[12.5px] font-medium text-[var(--ink)]">Recognition ready</p>
                <Badge variant={models.data?.recognition_ready ? "present" : "unknown"}>
                  {models.data?.recognition_ready ? "YES" : "NO"}
                </Badge>
              </div>
            </div>
          </AsyncState>
        </Panel>

        <Panel title="Dependencies" icon={<Database className="h-3.5 w-3.5" />}>
          <AsyncState isLoading={health.isLoading} error={health.error} rows={3}>
            <div className="divide-y divide-[var(--stone-100)]">
              {health.data?.checks.map((check) => (
                <div key={check.name} className="px-5 py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[12.5px] font-medium text-[var(--ink)]">{check.name}</p>
                    <p className="text-[10.5px] text-[var(--ink-faint)] truncate">{check.detail}</p>
                  </div>
                  <Badge variant={check.healthy ? "present" : "absent"}>
                    {check.healthy ? "UP" : "DOWN"}
                  </Badge>
                </div>
              ))}
              <div className="px-5 py-3 flex items-center justify-between gap-3">
                <p className="text-[12.5px] font-medium text-[var(--ink)]">API base URL</p>
                <span className="text-[11px] font-mono text-[var(--ink-faint)] truncate">{API_BASE_URL}</span>
              </div>
            </div>
          </AsyncState>
        </Panel>
      </div>

      <Panel title="Decision thresholds">
        <div className="px-5 py-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Threshold label="Match" value={threshold(models.data?.thresholds.match_threshold ?? null)} />
          <Threshold label="Review" value={threshold(models.data?.thresholds.review_threshold ?? null)} />
          <Threshold label="Minimum margin" value={threshold(models.data?.thresholds.minimum_margin ?? null)} />
        </div>
        <p className="px-5 pb-4 text-[11px] text-[var(--ink-faint)]">
          While any threshold is uncalibrated the API can only answer HUMAN_REVIEW or UNKNOWN, so no
          attendance is marked automatically.
        </p>
      </Panel>
    </div>
  );
}

function Panel({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)] overflow-hidden">
      <div className="px-5 py-3.5 border-b border-[var(--stone-100)] flex items-center gap-2 text-[var(--ink-faint)]">
        {icon}
        <h2 className="text-[10.5px] font-semibold uppercase tracking-widest">{title}</h2>
      </div>
      {children}
    </div>
  );
}

function Threshold({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[var(--stone-100)] px-4 py-3">
      <p className="text-[16px] font-bold text-[var(--ink)] leading-none tabular-nums">{value}</p>
      <p className="text-[10.5px] text-[var(--ink-faint)] mt-1.5">{label}</p>
    </div>
  );
}
