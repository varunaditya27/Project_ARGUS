import { api, query } from "./api";
import type { ClassSession, OffsetPage, SessionCloseReport, SessionCreate, SessionStatus } from "@/types";

export const sessionService = {
  listSessions(
    params: {
      classId?: string;
      status?: SessionStatus;
      dateFrom?: string;
      dateTo?: string;
      limit?: number;
      offset?: number;
    } = {}
  ) {
    return api.get<OffsetPage<ClassSession>>(
      `/sessions${query({
        class_id: params.classId,
        status: params.status,
        date_from: params.dateFrom,
        date_to: params.dateTo,
        limit: params.limit,
        offset: params.offset,
      })}`
    );
  },

  getSession(sessionId: string) {
    return api.get<ClassSession>(`/sessions/${sessionId}`);
  },

  /** At most one ACTIVE session per classroom; a second open is rejected. */
  createSession(input: SessionCreate) {
    return api.post<ClassSession>("/sessions", input);
  },

  /** Flushes the buffer, marks every unseen roster member Absent, closes. */
  closeSession(sessionId: string) {
    return api.post<SessionCloseReport>(`/sessions/${sessionId}/close`, {});
  },
};
