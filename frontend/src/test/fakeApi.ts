// A stand-in for the Transcribr API in component tests: register handlers per "METHOD /path",
// and every request is recorded so tests can check what the UI sent.

import type {
  Attribution,
  AuthState,
  CallDetail,
  CallList,
  CallListItem,
  People,
  Profile,
  QueueList,
  SettingsResponse,
  Status,
  Transcript,
} from "../api/hooks";

type Handler = (body: unknown, query: URLSearchParams) => { status?: number; body: unknown };

export interface SentRequest {
  method: string;
  path: string;
  query: URLSearchParams;
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
    sent.push({ method, path, query: url.searchParams, body, headers: (init.headers ?? {}) as Record<string, string> });
    const handler = handlers.get(`${method} ${path}`);
    if (!handler) {
      return new Response(JSON.stringify({ error: { code: "not_found", message: "Not Found" } }), {
        status: 404,
      });
    }
    const result = handler(body, url.searchParams);
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

export const DEFAULT_PROMPT =
  "Below is a phone call between our tire and auto shop and a customer. List what the customer asked for.";

export function settings(overrides: Partial<SettingsResponse["values"]> = {}): SettingsResponse {
  return {
    values: {
      store_queues: [],
      poll_interval_minutes: 2,
      time_zone: "America/Chicago",
      research_prompt: DEFAULT_PROMPT,
      voice_threshold_low: 0.5,
      voice_threshold_high: 0.65,
      ...overrides,
    },
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
      {
        key: "research_prompt",
        label: "Research prompt",
        message: "The research prompt must be 1 to 4,000 characters, and not only spaces.",
        default: DEFAULT_PROMPT,
        min_length: 1,
        max_length: 4000,
      },
      { key: "voice_threshold_low", label: "Weak voice match from", message: "Each voice threshold must be a number from 0 to 1." },
      { key: "voice_threshold_high", label: "Strong voice match from", message: "Each voice threshold must be a number from 0 to 1." },
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

export function call(overrides: Partial<CallListItem> = {}): CallListItem {
  return {
    id: 90012417,
    queue: "tireProz-salescustserv",
    start_local: "2026-10-22 11:41:00",
    start_utc: "2026-10-22T16:41:00Z",
    minutes: 4.6167,
    caller_number: "(405) 555-0187",
    answered_by: "SW Counter Sales",
    state: "transcribed",
    has_transcript: true,
    no_speech: false,
    attributions: [],
    passage: null,
    ...overrides,
  };
}

export function callList(calls: CallListItem[], nextCursor: string | null = null): CallList {
  return { calls, next_cursor: nextCursor };
}

export function callDetail(overrides: Partial<CallDetail> = {}): CallDetail {
  const { passage: _passage, ...summary } = call();
  return {
    ...summary,
    queue_label: "Stillwater Sales/CS (x600)",
    auto_queued: true,
    failure_reason: null,
    transcribed_at: "2026-10-22T16:47:00Z",
    language: "en",
    model: "small.en",
    ...overrides,
  };
}

export function transcript(overrides: Partial<Transcript> = {}): Transcript {
  return {
    call_id: 90012417,
    language: "en",
    model: "small.en",
    transcribed_at: "2026-10-22T16:47:00Z",
    no_speech: false,
    segments: [
      { idx: 0, start_s: 0, end_s: 3.5, text: "Thanks for calling, front counter.", has_voiceprint: true },
      { idx: 1, start_s: 4.2, end_s: 9.8, text: "I need tires for my 2019 Silverado.", has_voiceprint: true },
      { idx: 2, start_s: 65, end_s: 70, text: "About nine hundred for all four.", has_voiceprint: true },
    ],
    ...overrides,
  };
}

export function attribution(overrides: Partial<Attribution> = {}): Attribution {
  return {
    profile_id: 2,
    display_name: "Nolan",
    status: "confident",
    method: "name",
    name_heard: "Nolan",
    name_at_s: 2.5,
    voice_score: null,
    ...overrides,
  };
}

export function people(overrides: Partial<People> = {}): People {
  return {
    people: [
      { id: 2, display_name: "Nolan", calls: 14, maybe_calls: 3 },
      { id: 3, display_name: "Dana", calls: 6, maybe_calls: 0 },
    ],
    maybe_calls: 3,
    unassigned_calls: 9,
    ...overrides,
  };
}

export function profile(overrides: Partial<Profile> = {}): Profile {
  return {
    id: 2,
    display_name: "Nolan",
    variants: ["Nolan", "Nolen"],
    created_at: "2026-10-31T18:53:29Z",
    voice: { calls: 2, seconds: 20, usable: false, calls_needed: 1, seconds_needed: 10 },
    found: { name: 11, voice: 0, name_and_voice: 0, manual: 3, maybe: 3 },
    ...overrides,
  };
}
