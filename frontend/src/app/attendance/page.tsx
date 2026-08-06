"use client";

import React, { useState } from "react";
import { Search, FileSpreadsheet, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { MOCK_ATTENDANCE_RECORDS } from "@/mock/attendance-mock";
import { attendanceService } from "@/services/attendance";

export default function AttendancePage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [classFilter, setClassFilter] = useState("ALL");
  const [isExporting, setIsExporting] = useState(false);

  const filtered = MOCK_ATTENDANCE_RECORDS.filter((item) => {
    const matchesSearch =
      item.studentName.toLowerCase().includes(search.toLowerCase()) ||
      item.rollNumber.toLowerCase().includes(search.toLowerCase()) ||
      item.department.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === "ALL" || item.status === statusFilter;
    const matchesClass = classFilter === "ALL" || item.classSession.includes(classFilter);
    return matchesSearch && matchesStatus && matchesClass;
  });

  const handleExportCSV = async () => {
    setIsExporting(true);
    const csvContent = await attendanceService.exportAttendanceCSV();
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `ARGUS_Attendance_${new Date().toISOString().split("T")[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setIsExporting(false);
  };

  return (
    <div className="space-y-7">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Attendance</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">{filtered.length} records</p>
        </div>
        <Button variant="outline" size="sm" onClick={handleExportCSV} isLoading={isExporting}>
          <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5" />
          Export CSV
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-2 h-4 w-4 text-[var(--ink-faint)]" />
          <Input
            placeholder="Search student or department..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-40">
          <option value="ALL">All Statuses</option>
          <option value="PRESENT">Present</option>
          <option value="ABSENT">Absent</option>
          <option value="LATE">Late</option>
          <option value="UNKNOWN">Unknown</option>
        </Select>
        <Select value={classFilter} onChange={(e) => setClassFilter(e.target.value)} className="w-40">
          <option value="ALL">All Classes</option>
          <option value="CSE-101">CSE-101</option>
          <option value="AI-Lab">AI-Lab</option>
          <option value="ECE-204">ECE-204</option>
        </Select>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-[var(--stone-200)] overflow-hidden shadow-[0_1px_3px_rgba(15,27,53,0.05)]">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Roll No</TableHead>
              <TableHead>Student</TableHead>
              <TableHead>Department</TableHead>
              <TableHead>Time</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((record) => (
              <TableRow key={record.id}>
                <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)]">
                  {record.rollNumber}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2.5">
                    <Avatar name={record.studentName} size="sm" />
                    <span className="font-medium text-[12.5px] text-[var(--ink)]">{record.studentName}</span>
                  </div>
                </TableCell>
                <TableCell className="text-[12px] text-[var(--ink-muted)]">{record.department}</TableCell>
                <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)] tabular-nums">
                  {record.timestamp !== "2026-08-06T00:00:00Z"
                    ? new Date(record.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                    : "—"}
                </TableCell>
                <TableCell className="font-semibold text-[12.5px] text-[var(--ink)] tabular-nums">
                  {record.confidence > 0 ? `${(record.confidence * 100).toFixed(1)}%` : "—"}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={
                      record.status === "PRESENT" ? "present"
                      : record.status === "ABSENT" ? "absent"
                      : record.status === "LATE" ? "late"
                      : "unknown"
                    }
                  >
                    {record.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {/* Pagination */}
        <div className="px-5 py-3 flex items-center justify-between border-t border-[var(--stone-200)]">
          <span className="text-[11.5px] text-[var(--ink-faint)]">{filtered.length} records</span>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" disabled>
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            <Button variant="secondary" size="sm" className="bg-[var(--accent-light)] text-[var(--accent)] border-[var(--accent-light)]">1</Button>
            <Button variant="outline" size="icon" disabled>
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
