import { simulateDelay } from "./api";
import { MOCK_ATTENDANCE_RECORDS } from "@/mock/attendance-mock";
import { AttendanceRecord, RecognitionStatus } from "@/types";

let localAttendance = [...MOCK_ATTENDANCE_RECORDS];

export const attendanceService = {
  async getAttendanceRecords(filters?: {
    search?: string;
    classSession?: string;
    status?: RecognitionStatus;
  }): Promise<AttendanceRecord[]> {
    let records = [...localAttendance];
    if (filters?.search) {
      const q = filters.search.toLowerCase();
      records = records.filter(
        (r) =>
          r.studentName.toLowerCase().includes(q) ||
          r.rollNumber.toLowerCase().includes(q) ||
          r.department.toLowerCase().includes(q)
      );
    }
    if (filters?.status) {
      records = records.filter((r) => r.status === filters.status);
    }
    return simulateDelay(records, 250);
  },

  async markAttendance(record: Omit<AttendanceRecord, "id">): Promise<AttendanceRecord> {
    const newRecord: AttendanceRecord = {
      ...record,
      id: `att_${Date.now()}`,
    };
    localAttendance.unshift(newRecord);
    return simulateDelay(newRecord, 200);
  },

  async exportAttendanceCSV(): Promise<string> {
    const headers = "ID,Roll No,Student Name,Department,Time,Confidence,Status,Masked\n";
    const rows = localAttendance
      .map(
        (r) =>
          `"${r.id}","${r.rollNumber}","${r.studentName}","${r.department}","${r.timestamp}","${(r.confidence * 100).toFixed(1)}%","${r.status}","${r.isMasked}"`
      )
      .join("\n");
    return simulateDelay(headers + rows, 300);
  },
};
