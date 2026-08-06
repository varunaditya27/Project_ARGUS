"use client";

import React from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from "recharts";
import { MOCK_ATTENDANCE_TRENDS, MOCK_DEPARTMENT_STATS, MOCK_ACCURACY_TRENDS } from "@/mock/reports-mock";

export default function ReportsPage() {
  return (
    <div className="space-y-7">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Reports</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">Attendance and recognition analytics</p>
        </div>
        <Button variant="outline" size="sm">
          <Download className="h-3.5 w-3.5 mr-1.5" />
          Export Report
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* Weekly Attendance Chart */}
        <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
          <div className="px-5 py-4 border-b border-[var(--stone-100)]">
            <h2 className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
              Weekly Attendance
            </h2>
          </div>
          <div className="px-5 py-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={MOCK_ATTENDANCE_TRENDS} barSize={24}>
                <XAxis dataKey="day" stroke="#A8A49C" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke="#A8A49C" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#FFFFFF",
                    borderColor: "#E8E6E1",
                    borderRadius: "8px",
                    fontSize: "11px",
                    color: "#0F1B35",
                    boxShadow: "0 4px 12px rgba(15,27,53,0.1)",
                  }}
                />
                <Bar dataKey="present" fill="#2A52A3" radius={[3, 3, 0, 0]} name="Present" />
                <Bar dataKey="late" fill="#D4A44C" radius={[3, 3, 0, 0]} name="Late" />
                <Bar dataKey="absent" fill="#D4AAAA" radius={[3, 3, 0, 0]} name="Absent" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Accuracy Trends Chart */}
        <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
          <div className="px-5 py-4 border-b border-[var(--stone-100)]">
            <h2 className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
              Recognition Accuracy (%/hr)
            </h2>
          </div>
          <div className="px-5 py-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={MOCK_ACCURACY_TRENDS} barSize={16}>
                <XAxis dataKey="time" stroke="#A8A49C" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke="#A8A49C" fontSize={11} tickLine={false} axisLine={false} domain={[80, 100]} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#FFFFFF",
                    borderColor: "#E8E6E1",
                    borderRadius: "8px",
                    fontSize: "11px",
                    color: "#0F1B35",
                    boxShadow: "0 4px 12px rgba(15,27,53,0.1)",
                  }}
                />
                <Bar dataKey="argusEnhanced" fill="#2A52A3" radius={[3, 3, 0, 0]} name="ARGUS" />
                <Bar dataKey="maskedArcFace" fill="#A8A49C" radius={[3, 3, 0, 0]} name="Baseline Masked" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>

      {/* Department Stats Table */}
      <div className="rounded-xl border border-[var(--stone-200)] bg-white shadow-[0_1px_3px_rgba(15,27,53,0.05)] overflow-hidden">
        <div className="px-5 py-4 border-b border-[var(--stone-100)]">
          <h2 className="text-[10.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)]">
            Department Summary
          </h2>
        </div>
        <div className="divide-y divide-[var(--stone-100)]">
          {MOCK_DEPARTMENT_STATS.map((dept) => (
            <div key={dept.department} className="px-5 py-3.5 flex items-center justify-between hover:bg-[var(--stone-50)] transition-colors">
              <div>
                <p className="text-[12.5px] font-medium text-[var(--ink)]">{dept.department}</p>
                <p className="text-[11px] text-[var(--ink-faint)]">{dept.totalStudents} students</p>
              </div>
              <div className="flex items-center gap-8 text-right">
                <div>
                  <p className="text-[9.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-0.5">Attendance</p>
                  <p className="text-[14px] font-bold text-[var(--ink)]">{dept.attendancePercentage}%</p>
                </div>
                <div>
                  <p className="text-[9.5px] font-semibold uppercase tracking-widest text-[var(--ink-faint)] mb-0.5">Accuracy</p>
                  <p className="text-[14px] font-bold text-[var(--accent)]">{dept.accuracyPercentage}%</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
