import { simulateDelay } from "./api";
import { MOCK_CLASSROOMS } from "@/mock/sessions-mock";
import { Classroom } from "@/types";

let localClassrooms = [...MOCK_CLASSROOMS];

export const classroomService = {
  async getClassrooms(): Promise<Classroom[]> {
    return simulateDelay([...localClassrooms], 200);
  },

  async createClassroom(input: Omit<Classroom, "id" | "activeStudents">): Promise<Classroom> {
    const newClassroom: Classroom = {
      ...input,
      id: `cls_${Date.now()}`,
      activeStudents: 0,
    };
    localClassrooms.push(newClassroom);
    return simulateDelay(newClassroom, 300);
  },
};
