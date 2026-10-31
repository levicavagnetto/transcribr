// A thin wrapper over fetch for the Transcribr API: JSON in and out, the write header on every
// non-GET request (the server refuses writes without it), and the server's error format as ApiError.

export const API = "/api/v1";
const WRITE_HEADER = { "X-Transcribr": "1" };

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly key: string | undefined;
  readonly retryAfter: number | undefined;

  constructor(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.key = typeof extra.key === "string" ? extra.key : undefined;
    this.retryAfter = typeof extra.retry_after === "number" ? extra.retry_after : undefined;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = method === "GET" ? {} : { ...WRITE_HEADER };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "offline", "Can't reach the Transcribr server. Check that it is running.");
  }
  const text = await response.text();
  const data: unknown = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const error = (data as { error?: Record<string, unknown> } | null)?.error ?? {};
    throw new ApiError(
      response.status,
      typeof error.code === "string" ? error.code : `http_${response.status}`,
      typeof error.message === "string" ? error.message : response.statusText,
      error,
    );
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};
