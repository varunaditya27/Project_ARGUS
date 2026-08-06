import { create } from "zustand";

export interface ProcessingStep {
  id: string;
  label: string;
  status: "pending" | "processing" | "completed" | "failed";
}

interface EnrollmentState {
  capturedImageName: string | null;
  processingSteps: ProcessingStep[];
  isProcessing: boolean;
  isComplete: boolean;
  setCapturedImage: (name: string | null) => void;
  startEnrollmentProcess: () => void;
  resetEnrollment: () => void;
}

const INITIAL_STEPS: ProcessingStep[] = [
  { id: "step_1", label: "Face Detected & Aligned", status: "pending" },
  { id: "step_2", label: "Embedding Generated (ArcFace-R100)", status: "pending" },
  { id: "step_3", label: "Mask Variants Created (15 Synthetic)", status: "pending" },
  { id: "step_4", label: "Vector Stored in ChromaDB Collection", status: "pending" },
  { id: "step_5", label: "Student Record Stored in PostgreSQL", status: "pending" },
];

export const useEnrollmentStore = create<EnrollmentState>((set) => ({
  capturedImageName: null,
  processingSteps: INITIAL_STEPS,
  isProcessing: false,
  isComplete: false,
  setCapturedImage: (name) => set({ capturedImageName: name }),
  startEnrollmentProcess: () => {
    set({ isProcessing: true, isComplete: false });
    
    // Simulate step by step progress
    INITIAL_STEPS.forEach((step, index) => {
      setTimeout(() => {
        set((state) => {
          const updated = state.processingSteps.map((s, i) => {
            if (i < index + 1) return { ...s, status: "completed" as const };
            if (i === index + 1) return { ...s, status: "processing" as const };
            return s;
          });
          const allCompleted = index === INITIAL_STEPS.length - 1;
          return {
            processingSteps: updated,
            isProcessing: !allCompleted,
            isComplete: allCompleted,
          };
        });
      }, (index + 1) * 600);
    });
  },
  resetEnrollment: () =>
    set({
      capturedImageName: null,
      processingSteps: INITIAL_STEPS.map((s) => ({ ...s, status: "pending" })),
      isProcessing: false,
      isComplete: false,
    }),
}));
