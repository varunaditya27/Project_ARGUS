/**
 * ARGUS Mock API Service Layer
 * 
 * Architecture Note:
 * This layer abstracts all network requests. Currently returns mocked Promises.
 * To connect to the FastAPI backend later, simply update the base URL and fetch/axios implementation
 * inside this module without altering UI components.
 */

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export function simulateDelay<T>(data: T, delayMs: number = 300): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(data), delayMs);
  });
}
