import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

export const REFRESH_MS = 10_000;

export type RavonState =
  | "ok"
  | "login_failed"
  | "unreachable"
  | "no_credentials"
  | "page_format_changed"
  | "unknown";

export interface Status {
  worker_running: boolean;
  worker_last_seen: string | null;
  last_poll_ok: string | null;
  ravon_state: RavonState;
  ravon_error: string | null;
  queues_chosen: boolean;
  admin_exists: boolean;
  listed_today: number;
  transcribed_today: number;
  waiting: number;
  failed_last_24h: number;
  guard_violations: number;
}

export type AuthStateName = "setup_required" | "login_required" | "logged_in";

export interface AuthState {
  state: AuthStateName;
  username: string | null;
}

export interface SettingsValues {
  store_queues: string[];
  poll_interval_minutes: number;
  time_zone: string;
  research_prompt?: string;
  [key: string]: unknown;
}

export interface SettingField {
  key: string;
  label: string;
  message: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  min_length?: number;
  max_length?: number;
}

export interface SettingsResponse {
  values: SettingsValues;
  fields: SettingField[];
}

export interface QueueList {
  queues: { value: string; label: string }[];
  fetched_at: string | null;
  refresh_requested: boolean;
}

export type CallState = "not_transcribed" | "waiting" | "processing" | "transcribed" | "failed";

export interface PassagePart {
  text: string;
  hit: boolean;
}

// A person on a call. Rejected people are never listed; voiceprints never leave the server.
export interface Attribution {
  profile_id: number;
  display_name: string;
  status: "confident" | "maybe";
  method: "name" | "voice" | "name+voice" | "manual";
  name_heard: string | null;
  name_at_s: number | null;
  voice_score: number | null;
}

export interface CallSummary {
  id: number;
  queue: string;
  start_local: string;
  start_utc: string;
  minutes: number;
  caller_number: string;
  answered_by: string;
  state: CallState;
  has_transcript: boolean;
  no_speech: boolean;
  attributions: Attribution[];
}

export interface CallListItem extends CallSummary {
  passage: { at_s: number; parts: PassagePart[] } | null;
}

export interface CallList {
  calls: CallListItem[];
  next_cursor: string | null;
}

export interface CallDetail extends CallSummary {
  queue_label: string | null;
  auto_queued: boolean;
  failure_reason: string | null;
  transcribed_at: string | null;
  language: string | null;
  model: string | null;
}

export interface Segment {
  idx: number;
  start_s: number;
  end_s: number;
  text: string;
  has_voiceprint: boolean; // whether the admin can enroll this line for a person's voice
}

export interface Transcript {
  call_id: number;
  language: string;
  model: string;
  transcribed_at: string;
  no_speech: boolean;
  segments: Segment[];
}

export interface CallFilters {
  state?: CallState;
  from?: string;
  to?: string;
  q?: string;
  number?: string;
  person?: string; // a profile ID
  maybe?: "true";
  unassigned?: "true";
}

export interface Person {
  id: number;
  display_name: string;
  calls: number;
  maybe_calls: number;
}

export interface People {
  people: Person[];
  maybe_calls: number;
  unassigned_calls: number;
}

export interface VoiceProgress {
  calls: number;
  seconds: number;
  usable: boolean;
  calls_needed: number;
  seconds_needed: number;
}

export interface Profile {
  id: number;
  display_name: string;
  variants: string[];
  created_at: string;
  voice: VoiceProgress;
  found: { name: number; voice: number; name_and_voice: number; manual: number; maybe: number };
}

export interface Samples {
  voice: VoiceProgress;
  calls: { call_id: number; start_local: string; seconds: number; lines: { idx: number; start_s: number; end_s: number }[] }[];
}

export const keys = {
  status: ["status"] as const,
  auth: ["auth"] as const,
  settings: ["admin", "settings"] as const,
  queues: ["admin", "queues"] as const,
  calls: ["calls"] as const,
  callList: (filters: CallFilters) => ["calls", "list", filters] as const,
  call: (id: number) => ["calls", "one", id] as const,
  transcript: (id: number) => ["calls", "transcript", id] as const,
  researchPrompt: ["research-prompt"] as const,
  people: ["people"] as const,
  profiles: ["admin", "profiles"] as const,
  samples: (id: number) => ["admin", "profiles", id, "samples"] as const,
};

export function useStatus() {
  return useQuery({
    queryKey: keys.status,
    queryFn: () => api.get<Status>("/status"),
    refetchInterval: REFRESH_MS,
  });
}

export const PAGE_SIZE = 50;

function callListPath(filters: CallFilters, cursor: string | null): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  if (cursor) params.set("cursor", cursor);
  return `/calls?${params.toString()}`;
}

// Newest first, one page at a time; refetched every REFRESH_MS so new calls and state changes show up.
export function useCalls(filters: CallFilters) {
  return useInfiniteQuery({
    queryKey: keys.callList(filters),
    queryFn: ({ pageParam }) => api.get<CallList>(callListPath(filters, pageParam)),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    refetchInterval: REFRESH_MS,
  });
}

export function useCall(id: number) {
  return useQuery({
    queryKey: keys.call(id),
    queryFn: () => api.get<CallDetail>(`/calls/${id}`),
    refetchInterval: REFRESH_MS,
  });
}

export function useTranscript(id: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.transcript(id),
    queryFn: () => api.get<Transcript>(`/calls/${id}/transcript`),
    enabled,
  });
}

export function useResearchPrompt() {
  return useQuery({
    queryKey: keys.researchPrompt,
    queryFn: () => api.get<{ prompt: string }>("/research-prompt"),
  });
}

export function useTranscribe() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post<{ queued: boolean; state: CallState }>(`/calls/${id}/transcribe`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.calls });
      void client.invalidateQueries({ queryKey: keys.status });
    },
  });
}

export function useLoadEarlier() {
  return useMutation({ mutationFn: () => api.post<{ requested: boolean }>("/calls/load-earlier") });
}

export function useCheckRavon() {
  return useMutation({
    mutationFn: () => api.post<{ requested: boolean; last_poll_ok: string | null }>("/check-ravon"),
  });
}

export function useAuthState() {
  return useQuery({ queryKey: keys.auth, queryFn: () => api.get<AuthState>("/auth/state") });
}

export function useSettings(enabled: boolean) {
  return useQuery({
    queryKey: keys.settings,
    queryFn: () => api.get<SettingsResponse>("/admin/settings"),
    enabled,
  });
}

export function useQueues(enabled: boolean) {
  return useQuery({
    queryKey: keys.queues,
    queryFn: () => api.get<QueueList>("/admin/queues"),
    enabled,
    refetchInterval: (query) => (query.state.data?.refresh_requested ? 2_000 : REFRESH_MS),
  });
}

function useAuthMutation<Body>(path: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Body) => api.post<AuthState>(path, body),
    onSuccess: (state) => {
      client.setQueryData(keys.auth, state);
      void client.invalidateQueries({ queryKey: ["admin"] });
    },
  });
}

export const useLogin = () => useAuthMutation<{ username: string; password: string }>("/auth/login");
export const useSetup = () =>
  useAuthMutation<{ code: string; username: string; password: string }>("/auth/setup");

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<AuthState>("/auth/logout"),
    onSuccess: (state) => {
      client.setQueryData(keys.auth, state);
      client.removeQueries({ queryKey: ["admin"] });
    },
  });
}

export function useSaveSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (changes: Partial<SettingsValues>) => api.put<SettingsResponse>("/admin/settings", changes),
    onSuccess: (data) => {
      client.setQueryData(keys.settings, data);
      void client.invalidateQueries({ queryKey: keys.status });
      void client.invalidateQueries({ queryKey: keys.researchPrompt });
    },
  });
}

export function useRefreshQueues() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ requested: boolean }>("/admin/queues/refresh"),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.queues }),
  });
}

export function useRetryLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ requested: boolean }>("/admin/ravon/retry-login"),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.status }),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current: string; new: string }) =>
      api.post<{ changed: boolean }>("/admin/password", body),
  });
}

export function usePeople() {
  return useQuery({ queryKey: keys.people, queryFn: () => api.get<People>("/people"), refetchInterval: REFRESH_MS });
}

// Attribution changes move calls between filters, so the lists and counts are refetched.
function useAttributionChange<Args>(fn: (args: Args) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.calls });
      void client.invalidateQueries({ queryKey: keys.people });
      void client.invalidateQueries({ queryKey: keys.profiles });
    },
  });
}

export const useClaim = () =>
  useAttributionChange(({ call, person }: { call: number; person: number }) =>
    api.post(`/calls/${call}/attributions`, { profile_id: person }),
  );
export const useReject = () =>
  useAttributionChange(({ call, person }: { call: number; person: number }) =>
    api.delete(`/calls/${call}/attributions/${person}`),
  );
export const useConfirm = () =>
  useAttributionChange(({ call, person }: { call: number; person: number }) =>
    api.post(`/calls/${call}/attributions/${person}/confirm`),
  );

export function useProfiles(enabled = true) {
  return useQuery({
    queryKey: keys.profiles,
    queryFn: () => api.get<{ profiles: Profile[] }>("/admin/profiles"),
    enabled,
    refetchInterval: REFRESH_MS,
  });
}

export function useSamples(id: number) {
  return useQuery({ queryKey: keys.samples(id), queryFn: () => api.get<Samples>(`/admin/profiles/${id}/samples`) });
}

export interface ProfileIn {
  display_name: string;
  variants: string[];
}

export const useCreateProfile = () =>
  useAttributionChange((body: ProfileIn) => api.post<Profile>("/admin/profiles", body));
export const useUpdateProfile = () =>
  useAttributionChange(({ id, ...body }: ProfileIn & { id: number }) => api.put<Profile>(`/admin/profiles/${id}`, body));
export const useDeleteProfile = () => useAttributionChange((id: number) => api.delete(`/admin/profiles/${id}`));
export const useEnroll = () =>
  useAttributionChange(({ person, call, lines }: { person: number; call: number; lines: number[] }) =>
    api.post<Samples>(`/admin/profiles/${person}/samples`, { call_id: call, lines }),
  );
export const useRemoveSamples = () =>
  useAttributionChange(({ person, call }: { person: number; call: number }) =>
    api.delete<Samples>(`/admin/profiles/${person}/samples/${call}`),
  );
