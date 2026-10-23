import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
  [key: string]: unknown;
}

export interface SettingField {
  key: string;
  label: string;
  message: string;
  minimum?: number;
  maximum?: number;
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

export const keys = {
  status: ["status"] as const,
  auth: ["auth"] as const,
  settings: ["admin", "settings"] as const,
  queues: ["admin", "queues"] as const,
};

export function useStatus() {
  return useQuery({
    queryKey: keys.status,
    queryFn: () => api.get<Status>("/status"),
    refetchInterval: REFRESH_MS,
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
