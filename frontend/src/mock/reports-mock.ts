import { AccuracyTrendPoint, AttendanceTrendPoint, DepartmentStat, ModelSettings } from "@/types";

export const MOCK_ACCURACY_TRENDS: AccuracyTrendPoint[] = [
  { time: "09:00", baselineUnmasked: 99.2, maskedArcFace: 84.1, argusEnhanced: 98.4 },
  { time: "09:15", baselineUnmasked: 99.1, maskedArcFace: 83.5, argusEnhanced: 97.9 },
  { time: "09:30", baselineUnmasked: 99.4, maskedArcFace: 85.0, argusEnhanced: 98.6 },
  { time: "09:45", baselineUnmasked: 99.0, maskedArcFace: 82.9, argusEnhanced: 97.6 },
  { time: "10:00", baselineUnmasked: 99.3, maskedArcFace: 84.8, argusEnhanced: 98.2 },
  { time: "10:15", baselineUnmasked: 99.5, maskedArcFace: 85.3, argusEnhanced: 98.8 },
];

export const MOCK_ATTENDANCE_TRENDS: AttendanceTrendPoint[] = [
  { day: "Mon", present: 295, absent: 25, late: 10 },
  { day: "Tue", present: 310, absent: 15, late: 5 },
  { day: "Wed", present: 302, absent: 20, late: 8 },
  { day: "Thu", present: 288, absent: 22, late: 20 },
  { day: "Fri", present: 315, absent: 10, late: 5 },
];

export const MOCK_DEPARTMENT_STATS: DepartmentStat[] = [
  { department: "Computer Science", totalStudents: 140, attendancePercentage: 94.2, accuracyPercentage: 98.6 },
  { department: "Artificial Intelligence", totalStudents: 85, attendancePercentage: 96.1, accuracyPercentage: 97.9 },
  { department: "Electronics & Comm.", totalStudents: 95, attendancePercentage: 90.5, accuracyPercentage: 96.8 },
];

export const DEFAULT_MODEL_SETTINGS: ModelSettings = {
  detectorModel: "SCRFD-10G (InsightFace)",
  backboneModel: "ArcFace-ResNet100 (Fine-Tuned)",
  similarityThreshold: 0.72,
  maskSynthesisVariants: 15,
  unknownRejectionThreshold: 0.45,
  enableRealtimeEnhancement: true,
};
