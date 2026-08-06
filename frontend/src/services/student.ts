import { api, query } from "./api";
import type {
  EnrollmentResult,
  KeysetPage,
  OffsetPage,
  Student,
  StudentAttendanceRecord,
  StudentCreate,
  StudentTemplates,
  UploadedImage,
} from "@/types";

export const studentService = {
  /** Keyset page of the roster, ordered by roll number. */
  listStudents(params: { classId?: string; after?: number; limit?: number } = {}) {
    return api.get<KeysetPage<Student>>(
      `/students${query({ class_id: params.classId, after: params.after, limit: params.limit })}`
    );
  },

  getStudent(studentId: string) {
    return api.get<Student>(`/students/${studentId}`);
  },

  /** Stores an image and returns the URL to pass as image_url. */
  uploadImage(image: Blob, filename = "capture.jpg") {
    const form = new FormData();
    form.append("image", image, filename);
    return api.postForm<UploadedImage>("/students/image", form);
  },

  createStudent(input: StudentCreate) {
    return api.post<Student>("/students", input);
  },

  deleteStudent(studentId: string) {
    return api.delete<{ student_id: string; templates_removed: number }>(`/students/${studentId}`);
  },

  /** Builds the unmasked template plus every synthetic masked variant. */
  enrollFace(studentId: string, image: Blob, filename = "enrollment.jpg") {
    const form = new FormData();
    form.append("image", image, filename);
    return api.postForm<EnrollmentResult>(`/students/${studentId}/enroll`, form);
  },

  listTemplates(studentId: string) {
    return api.get<StudentTemplates>(`/students/${studentId}/templates`);
  },

  attendanceHistory(studentId: string, params: { limit?: number; offset?: number } = {}) {
    return api.get<OffsetPage<StudentAttendanceRecord>>(
      `/students/${studentId}/attendance${query({ ...params })}`
    );
  },

  /** Bulk roster registration from a CSV plus an optional ZIP of photographs. */
  importRoster(input: { csv: File; images?: File | null; classId?: string; dryRun?: boolean }) {
    const form = new FormData();
    form.append("csv_file", input.csv);
    if (input.images) form.append("images", input.images);
    if (input.classId) form.append("class_id", input.classId);
    form.append("dry_run", String(input.dryRun ?? false));
    return api.postForm<import("@/types").ImportReport>("/students/import", form);
  },
};
