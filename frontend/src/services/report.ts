import { attendanceService } from "./attendance";
import { classroomService } from "./classroom";
import { sessionService } from "./session";
import type { AttendanceSummary, ClassSession, Classroom } from "@/types";

export interface SessionReport {
  session: ClassSession;
  classroom?: Classroom;
  summary: AttendanceSummary;
  /** Present as a share of the roster; null while the roster is empty. */
  rate: number | null;
}

export interface DepartmentReport {
  department: string;
  sessions: number;
  present: number;
  absent: number;
  rate: number | null;
}

function rateOf(summary: AttendanceSummary): number | null {
  return summary.roster_count > 0 ? (summary.present / summary.roster_count) * 100 : null;
}

export const reportService = {
  /** Per-session present/absent, joined to the classroom that ran it.
   *
   * The backend exposes no analytics endpoints, so a report is assembled from
   * the session list plus one attendance summary per session.
   */
  async sessionReports(limit = 25): Promise<SessionReport[]> {
    const [sessions, classrooms] = await Promise.all([
      sessionService.listSessions({ limit }),
      classroomService.listClassrooms({ limit: 200 }),
    ]);
    const byId = new Map(classrooms.items.map((room) => [room.class_id, room]));
    const summaries = await Promise.all(
      sessions.items.map((session) => attendanceService.summary(session.session_id))
    );
    return sessions.items.map((session, index) => ({
      session,
      classroom: byId.get(session.class_id),
      summary: summaries[index],
      rate: rateOf(summaries[index]),
    }));
  },

  /** Rolls the session reports up by the classroom's department. */
  byDepartment(reports: SessionReport[]): DepartmentReport[] {
    const totals = new Map<string, DepartmentReport>();
    for (const report of reports) {
      const department = report.classroom?.department ?? "Unassigned";
      const row = totals.get(department) ?? {
        department,
        sessions: 0,
        present: 0,
        absent: 0,
        rate: null,
      };
      row.sessions += 1;
      row.present += report.summary.present;
      row.absent += report.summary.absent;
      totals.set(department, row);
    }
    return [...totals.values()].map((row) => ({
      ...row,
      rate: row.present + row.absent > 0 ? (row.present / (row.present + row.absent)) * 100 : null,
    }));
  },
};
