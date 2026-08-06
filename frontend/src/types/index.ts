export type EnrollmentStatus = "ENROLLED" | "PENDING" | "PROCESSING" | "FAILED";
export type RecognitionStatus = "PRESENT" | "ABSENT" | "LATE" | "UNKNOWN" | "HUMAN_REVIEW";
export type SessionStatus = "ACTIVE" | "UPCOMING" | "COMPLETED" | "CANCELLED";

export interface Student {
  id: string;
  rollNumber: string;
  name: string;
  email: string;
  department: string;
  enrollmentDate: string;
  status: EnrollmentStatus;
  maskVariantsCount: number;
  hasVectorEmbedding: boolean;
  recognitionAccuracy: number;
  lastSeen?: string;
  classroom?: string;
}

export interface StudentCreateInput {
  name: string;
  rollNumber: string;
  email: string;
  department: string;
  classroom?: string;
}

export interface AttendanceRecord {
  id: string;
  studentId: string;
  studentName: string;
  rollNumber: string;
  department: string;
  timestamp: string;
  confidence: number;
  status: RecognitionStatus;
  isMasked: boolean;
  classSession: string;
  location: string;
}

export interface BoundingBox {
  x: number; // percentage 0-100
  y: number; // percentage 0-100
  width: number; // percentage 0-100
  height: number; // percentage 0-100
  id: string;
  label: string;
  confidence: number;
  status: RecognitionStatus;
  isMasked: boolean;
}

export interface DetectionOverlay {
  id: string;
  timestamp: string;
  boxes: BoundingBox[];
}

export interface LiveMetrics {
  fps: number;
  latencyMs: number;
  activeDetections: number;
  systemStatus: "ACTIVE" | "STANDBY" | "ERROR";
  gpuUsage: number;
  cpuUsage: number;
}

export interface ClassSession {
  id: string;
  courseCode: string;
  courseName: string;
  facultyName: string;
  classroom: string;
  startTime: string;
  endTime: string;
  status: SessionStatus;
  enrolledStudentsCount: number;
  presentCount: number;
  absentCount: number;
  lateCount: number;
}

export interface Classroom {
  id: string;
  name: string;
  code: string;
  capacity: number;
  assignedFaculty: string;
  cameraId: string;
  status: "ONLINE" | "OFFLINE" | "MAINTENANCE";
  activeStudents: number;
}

export interface AccuracyTrendPoint {
  time: string;
  baselineUnmasked: number;
  maskedArcFace: number;
  argusEnhanced: number;
}

export interface AttendanceTrendPoint {
  day: string;
  present: number;
  absent: number;
  late: number;
}

export interface DepartmentStat {
  department: string;
  totalStudents: number;
  attendancePercentage: number;
  accuracyPercentage: number;
}

export interface NotificationItem {
  id: string;
  title: string;
  message: string;
  time: string;
  type: "info" | "warning" | "success" | "error";
  read: boolean;
}

export interface ModelSettings {
  detectorModel: string;
  backboneModel: string;
  similarityThreshold: number;
  maskSynthesisVariants: number;
  unknownRejectionThreshold: number;
  enableRealtimeEnhancement: boolean;
}
