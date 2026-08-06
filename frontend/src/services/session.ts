import { simulateDelay } from "./api";
import { MOCK_SESSIONS } from "@/mock/sessions-mock";
import { ClassSession } from "@/types";

let localSessions = [...MOCK_SESSIONS];

export const sessionService = {
  async getSessions(): Promise<ClassSession[]> {
    return simulateDelay([...localSessions], 200);
  },

  async createSession(session: Omit<ClassSession, "id" | "presentCount" | "absentCount" | "lateCount">): Promise<ClassSession> {
    const newSession: ClassSession = {
      ...session,
      id: `ses_${Date.now()}`,
      presentCount: 0,
      absentCount: 0,
      lateCount: 0,
    };
    localSessions.unshift(newSession);
    return simulateDelay(newSession, 300);
  },

  async deleteSession(id: string): Promise<{ success: boolean }> {
    localSessions = localSessions.filter((s) => s.id !== id);
    return simulateDelay({ success: true }, 250);
  },
};
