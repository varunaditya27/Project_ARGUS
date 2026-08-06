import React from "react";

/** Label above a form control, used by the create dialogs. */
export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-[12px] font-semibold text-[var(--ink)]">{label}</label>
      {children}
      {hint ? <p className="text-[10.5px] text-[var(--ink-faint)]">{hint}</p> : null}
    </div>
  );
}
