import { simulateDelay } from "./api";
import { MOCK_STUDENTS } from "@/mock/students-mock";
import { Student, StudentCreateInput } from "@/types";

let localStudents = [...MOCK_STUDENTS];

export const studentService = {
  async getStudents(): Promise<Student[]> {
    return simulateDelay([...localStudents], 250);
  },

  async getStudentById(id: string): Promise<Student | undefined> {
    const student = localStudents.find((s) => s.id === id);
    return simulateDelay(student, 200);
  },

  async createStudent(input: StudentCreateInput): Promise<Student> {
    const newStudent: Student = {
      id: `std_${Date.now()}`,
      rollNumber: input.rollNumber,
      name: input.name,
      email: input.email,
      department: input.department,
      enrollmentDate: new Date().toISOString().split("T")[0],
      status: "PROCESSING",
      maskVariantsCount: 15,
      hasVectorEmbedding: true,
      recognitionAccuracy: 97.5,
      classroom: input.classroom || "CSE-101",
    };
    localStudents.unshift(newStudent);
    return simulateDelay(newStudent, 400);
  },

  async updateStudent(id: string, update: Partial<Student>): Promise<Student> {
    localStudents = localStudents.map((s) => (s.id === id ? { ...s, ...update } : s));
    const updated = localStudents.find((s) => s.id === id)!;
    return simulateDelay(updated, 300);
  },

  async deleteStudent(id: string): Promise<{ success: boolean }> {
    localStudents = localStudents.filter((s) => s.id !== id);
    return simulateDelay({ success: true }, 300);
  },

  async enrollFaceImages(studentId: string, imageFiles: File[] | string[]): Promise<{ status: string; variantsGenerated: number }> {
    return simulateDelay({ status: "COMPLETED", variantsGenerated: 15 }, 600);
  },
};
