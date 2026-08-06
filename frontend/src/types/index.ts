/**
 * Wire types, mirroring the backend schemas in backend/app/schemas.
 *
 * Field names are the API's own (snake_case): no shadow model, so a payload can
 * be read straight from the network tab and matched against what a page renders.
 * Nothing here exists that the backend cannot supply.
 */

export type AttendanceStatus = "PRESENT" | "ABSENT";
export type SessionStatus = "ACTIVE" | "CLOSED";
export type DecisionState = "MATCH" | "HUMAN_REVIEW" | "UNKNOWN";

export interface KeysetPage<T> {
  items: T[];
  next_cursor: number | null;
}

export interface OffsetPage<T> {
  items: T[];
  limit: number;
  offset: number;
}

export interface Classroom {
  class_id: string;
  class_name: string;
  department: string;
  semester: number;
  strength: number;
}

export interface ClassroomDetail extends Classroom {
  /** Students actually assigned; attendance maths uses this, not `strength`. */
  roster_count: number;
}

export interface ClassroomCreate {
  class_name: string;
  department: string;
  semester: number;
  strength: number;
}

export interface Student {
  student_id: string;
  student_name: string;
  roll_no: number;
  class_id: string | null;
  image_url: string;
  created_at: string;
}

export interface StudentCreate {
  student_name: string;
  roll_no: number;
  class_id?: string | null;
  image_url: string;
}

export interface UploadedImage {
  key: string;
  url: string;
}

export interface StudentTemplates {
  student_id: string;
  templates: string[];
}

export interface EnrollmentResult {
  student_id: string;
  templates_stored: number;
  stored_variants: string[];
}

export interface ClassSession {
  session_id: string;
  class_id: string;
  subject: string;
  faculty: string;
  date: string;
  start_time: string;
  end_time: string;
  status: SessionStatus;
}

export interface SessionCreate {
  class_id: string;
  subject: string;
  faculty: string;
  date: string;
  start_time: string;
  end_time: string;
}

export interface SessionCloseReport {
  session_id: string;
  closed_at: string;
  present: number;
  absent_marked: number;
  roster_count: number;
}

export interface AttendanceRecord {
  attendance_id: string;
  student_id: string;
  student_name: string;
  roll_no: number;
  timestamp: string;
  confidence: number;
  status: AttendanceStatus;
}

export interface StudentAttendanceRecord {
  session_id: string;
  subject: string;
  date: string;
  timestamp: string;
  confidence: number;
  status: AttendanceStatus;
}

export interface AttendanceSummary {
  session_id: string;
  session_status: SessionStatus;
  roster_count: number;
  present: number;
  absent: number;
}

export interface FaceDecision {
  bbox: [number, number, number, number];
  detection_score: number;
  state: DecisionState;
  student_id: string | null;
  similarity: number | null;
  reason: string;
  attendance_recorded: boolean;
}

export interface FrameResult {
  frame_id: string;
  session_id: string | null;
  faces: FaceDecision[];
}

export interface ComponentStatus {
  name: string;
  configured: boolean;
  detail: string;
}

export interface ModelsResponse {
  components: ComponentStatus[];
  thresholds: {
    match_threshold: number | null;
    review_threshold: number | null;
    minimum_margin: number | null;
  };
  recognition_ready: boolean;
}

export interface HealthCheck {
  name: string;
  healthy: boolean;
  detail: string;
}

export interface HealthResponse {
  status: string;
  checks: HealthCheck[];
}

export interface ImportRowError {
  row: number;
  roll_no: number | null;
  reason: string;
}

export interface ImportReport {
  received_rows: number;
  created: number;
  skipped: number;
  dry_run: boolean;
  uploaded_images: number;
  errors: ImportRowError[];
  errors_truncated: boolean;
}
