/**
 * HTTP client for the ARGUS backend.
 *
 * Every service module goes through here so the base URL, the shared error
 * envelope and JSON handling live in one place.
 */

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

/** Error envelope the backend returns for every failure. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {}
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  // Prefer the backend envelope; fall back to the status line.
  try {
    const body = await response.json();
    const error = body?.error;
    if (error?.code) {
      return new ApiError(response.status, error.code, error.message, error.details ?? {});
    }
  } catch {
    // Not JSON - fall through.
  }
  return new ApiError(response.status, "http_error", `Request failed (${response.status})`);
}

async function request<T>(path: string, init?: RequestInit, allowStatus: number[] = []): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "network_error", "The backend is unreachable.");
  }
  if (!response.ok && !allowStatus.includes(response.status)) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  /** allowStatus keeps the body of a reply like /health's 503 instead of throwing. */
  get: <T>(path: string, allowStatus: number[] = []) => request<T>(path, undefined, allowStatus),

  post: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  postForm: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),

  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export function liveSocketUrl(sessionId?: string): string {
  // ws:// twin of the REST base URL.
  const base = API_BASE_URL.replace(/^http/, "ws");
  return sessionId ? `${base}/live?session_id=${sessionId}` : `${base}/live`;
}

export function query(params: Record<string, string | number | undefined | null>): string {
  // Drop empty values so optional filters never reach the API as "undefined".
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}
