import { simulateDelay } from "./api";
import { MOCK_ACCURACY_TRENDS, MOCK_ATTENDANCE_TRENDS, MOCK_DEPARTMENT_STATS } from "@/mock/reports-mock";
import { AccuracyTrendPoint, AttendanceTrendPoint, DepartmentStat } from "@/types";

export const reportService = {
  async getAccuracyTrends(): Promise<AccuracyTrendPoint[]> {
    return simulateDelay(MOCK_ACCURACY_TRENDS, 200);
  },

  async getAttendanceTrends(): Promise<AttendanceTrendPoint[]> {
    return simulateDelay(MOCK_ATTENDANCE_TRENDS, 200);
  },

  async getDepartmentStats(): Promise<DepartmentStat[]> {
    return simulateDelay(MOCK_DEPARTMENT_STATS, 200);
  },
};
