"use client";

import React, { useState } from "react";
import { Search, UserPlus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { MOCK_STUDENTS } from "@/mock/students-mock";
import { Student } from "@/types";

export default function StudentsPage() {
  const [students, setStudents] = useState<Student[]>(MOCK_STUDENTS);
  const [search, setSearch] = useState("");
  const [deptFilter, setDeptFilter] = useState("ALL");
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newStudent, setNewStudent] = useState({
    name: "",
    rollNumber: "",
    email: "",
    department: "Computer Science & Eng.",
  });

  const filtered = students.filter((s) => {
    const matchesSearch =
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.rollNumber.toLowerCase().includes(search.toLowerCase()) ||
      s.email.toLowerCase().includes(search.toLowerCase());
    const matchesDept = deptFilter === "ALL" || s.department === deptFilter;
    return matchesSearch && matchesDept;
  });

  const handleCreateStudent = () => {
    if (!newStudent.name || !newStudent.rollNumber) return;
    const created: Student = {
      id: `std_${Date.now()}`,
      rollNumber: newStudent.rollNumber,
      name: newStudent.name,
      email: newStudent.email || `${newStudent.name.toLowerCase().replace(" ", ".")}@argus.edu`,
      department: newStudent.department,
      enrollmentDate: new Date().toISOString().split("T")[0],
      status: "ENROLLED",
      maskVariantsCount: 15,
      hasVectorEmbedding: true,
      recognitionAccuracy: 97.5,
    };
    setStudents([created, ...students]);
    setIsAddModalOpen(false);
    setNewStudent({ name: "", rollNumber: "", email: "", department: "Computer Science & Eng." });
  };

  const handleDeleteStudent = (id: string) => {
    setStudents(students.filter((s) => s.id !== id));
  };

  return (
    <div className="space-y-7">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-[var(--ink)] tracking-tight leading-tight">Students</h1>
          <p className="text-[12.5px] text-[var(--ink-faint)] mt-0.5">{filtered.length} of {students.length} enrolled</p>
        </div>
        <Button onClick={() => setIsAddModalOpen(true)} variant="primary" size="sm">
          <UserPlus className="h-3.5 w-3.5 mr-1.5" />
          Add Student
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-2 h-4 w-4 text-[var(--ink-faint)]" />
          <Input
            placeholder="Search by name or roll number..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={deptFilter} onChange={(e) => setDeptFilter(e.target.value)} className="w-52">
          <option value="ALL">All Departments</option>
          <option value="Computer Science & Eng.">Computer Science & Eng.</option>
          <option value="Artificial Intelligence">Artificial Intelligence</option>
          <option value="Electronics & Comm.">Electronics & Comm.</option>
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
              <TableHead>Mask Variants</TableHead>
              <TableHead>Index Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((student) => (
              <TableRow key={student.id}>
                <TableCell className="font-mono text-[11.5px] text-[var(--ink-faint)]">
                  {student.rollNumber}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2.5">
                    <Avatar name={student.name} size="sm" />
                    <div>
                      <p className="font-medium text-[12.5px] text-[var(--ink)]">{student.name}</p>
                      <p className="text-[10.5px] text-[var(--ink-faint)]">{student.email}</p>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-[12px] text-[var(--ink-muted)]">{student.department}</TableCell>
                <TableCell className="font-semibold text-[12.5px] text-[var(--ink)]">{student.maskVariantsCount}</TableCell>
                <TableCell>
                  <Badge variant={student.hasVectorEmbedding ? "present" : "secondary"}>
                    {student.hasVectorEmbedding ? "Indexed" : "Pending"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <button
                    onClick={() => handleDeleteStudent(student.id)}
                    className="text-[var(--ink-faint)] hover:text-[var(--status-absent)] transition-colors p-1 rounded"
                    title="Remove Student"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Add Student Modal */}
      <Dialog open={isAddModalOpen} onOpenChange={setIsAddModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Register Student</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-[12px] font-semibold text-[var(--ink)]">Full Name</label>
              <Input
                placeholder="Full name"
                value={newStudent.name}
                onChange={(e) => setNewStudent({ ...newStudent, name: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[12px] font-semibold text-[var(--ink)]">Roll Number</label>
              <Input
                placeholder="e.g. CS2024001"
                value={newStudent.rollNumber}
                onChange={(e) => setNewStudent({ ...newStudent, rollNumber: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[12px] font-semibold text-[var(--ink)]">Department</label>
              <Select
                value={newStudent.department}
                onChange={(e) => setNewStudent({ ...newStudent, department: e.target.value })}
              >
                <option value="Computer Science & Eng.">Computer Science & Eng.</option>
                <option value="Artificial Intelligence">Artificial Intelligence</option>
                <option value="Electronics & Comm.">Electronics & Comm.</option>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setIsAddModalOpen(false)}>Cancel</Button>
            <Button variant="primary" size="sm" onClick={handleCreateStudent}>Register</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
