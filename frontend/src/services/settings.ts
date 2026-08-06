import { simulateDelay } from "./api";
import { DEFAULT_MODEL_SETTINGS } from "@/mock/reports-mock";
import { ModelSettings } from "@/types";

let currentSettings = { ...DEFAULT_MODEL_SETTINGS };

export const settingsService = {
  async getSettings(): Promise<ModelSettings> {
    return simulateDelay({ ...currentSettings }, 150);
  },

  async updateSettings(update: Partial<ModelSettings>): Promise<ModelSettings> {
    currentSettings = { ...currentSettings, ...update };
    return simulateDelay({ ...currentSettings }, 300);
  },
};
