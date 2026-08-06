import { api, query } from "./api";
import type { Classroom, ClassroomCreate, ClassroomDetail, OffsetPage } from "@/types";

export const classroomService = {
  listClassrooms(params: { limit?: number; offset?: number } = {}) {
    return api.get<OffsetPage<Classroom>>(`/classrooms${query({ ...params })}`);
  },

  /** Adds roster_count, which is the number attendance maths actually uses. */
  getClassroom(classId: string) {
    return api.get<ClassroomDetail>(`/classrooms/${classId}`);
  },

  createClassroom(input: ClassroomCreate) {
    return api.post<Classroom>("/classrooms", input);
  },
};
