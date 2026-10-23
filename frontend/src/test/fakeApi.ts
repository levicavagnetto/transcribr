// A stand-in for the Transcribr API in component tests: register handlers per "METHOD /path",
// and every request is recorded so tests can check what the UI sent.

import type { AuthState, QueueList, SettingsResponse, Status } from "../api/hooks";

type Handler = (body: unknown) => { status?: number; body: unknown };

export interface SentRequest {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

export interface FakeApi {
  on(route: string, handler: Handler | unknown): void;
  sent: SentRequest[];
}

export function installFakeApi(): FakeApi {
  const handlers = new Map<string, Handler>();
  const sent: SentRequest[] = [];
  const fakeFetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const body: unknown = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    sent.push({ method, path, body, headers: (init.headers ?? {}) as Record<string, string> });
    const handler = handlers.get(`${method} ${path}`);
    if (!handler) {
      return new Response(JSON.stringify({ error: { code: "not_found", message: "Not Found" } }), {
        status: 404,
      });
    }
    const result = handler(body);
    return new Response(JSON.stringify(result.body), { status: result.status ?? 200 });
  };
  vi.stubGlobal("fetch", vi.fn(fakeFetch));
  return {
    on(route, handler) {
      handlers.set(route, typeof handler === "function" ? (handler as Handler) : () => ({ body: handler }));
    },
    sent,
  };
}

export function status(overrides: Partial<Status> = {}): Status {
  return {
    worker_running: true,
    worker_last_seen: "2026-10-22T14:00:00Z",
    last_poll_ok: "2026-10-22T14:00:00Z",
    ravon_state: "ok",
    ravon_error: null,
    queues_chosen: true,
    admin_exists: true,
    listed_today: 15,
    transcribed_today: 12,
    waiting: 2,
    failed_last_24h: 1,
    guard_violations: 0,
    ...overrides,
  };
}

export const auth = (state: AuthState["state"], username: string | null = null): AuthState => ({
  state,
  username: state === "logged_in" ? (username ?? "admin") : null,
});

export function settings(overrides: Partial<SettingsResponse["values"]> = {}): SettingsResponse {
  return {
    values: { store_queues: [], poll_interval_minutes: 2, time_zone: "America/Chicago", ...overrides },
    fields: [
      { key: "store_queues", label: "Store queues", message: "Invalid value." },
      {
        key: "poll_interval_minutes",
        label: "Check for new calls every (minutes)",
        message: "The poll interval must be a whole number of minutes between 1 and 30.",
        minimum: 1,
        maximum: 30,
      },
      { key: "time_zone", label: "Store time zone", message: "Unknown time zone." },
    ],
  };
}

export function queueList(overrides: Partial<QueueList> = {}): QueueList {
  return {
    queues: [
      { value: "tireProz-salescustserv", label: "Stillwater Sales/CS (x600)" },
      { value: "tireProz-SWafterHRS", label: "SWafterHRS (x599)" },
      { value: "tireProz-hudsales", label: "Hudson Sales/CS (x700)" },
    ],
    fetched_at: "2026-10-22T14:00:00Z",
    refresh_requested: false,
    ...overrides,
  };
}
