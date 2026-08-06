import { api, query } from "./api";
import type { AttendanceRecord, AttendanceStatus, AttendanceSummary, KeysetPage } from "@/types";

export const attendanceService = {
  /** Keyset page of one session's register, ordered by roll number. */
  register(
    sessionId: string,
    params: { status?: AttendanceStatus; after?: number; limit?: number } = {}
  ) {
    return api.get<KeysetPage<AttendanceRecord>>(
      `/sessions/${sessionId}/attendance${query({ ...params })}`
    );
  },

  summary(sessionId: string) {
    return api.get<AttendanceSummary>(`/sessions/${sessionId}/attendance/summary`);
  },

  /** Walks every page so an export covers the whole register, not one page. */
  async registerAll(sessionId: string, pageSize = 200) {
    const rows: AttendanceRecord[] = [];
    let after: number | undefined;
    for (;;) {
      const page = await attendanceService.register(sessionId, { after, limit: pageSize });
      rows.push(...page.items);
      if (page.next_cursor === null) return rows;
      after = page.next_cursor;
    }
  },

  toCsv(rows: AttendanceRecord[]) {
    // Absent rows carry the close instant and a zero confidence, by design.
    const header = "roll_no,student_name,status,timestamp,confidence";
    const body = rows.map((row) =>
      [
        row.roll_no,
        `"${row.student_name.replace(/"/g, '""')}"`,
        row.status,
        row.timestamp,
        row.confidence.toFixed(4),
      ].join(",")
    );
    return [header, ...body].join("\n");
  },
};
