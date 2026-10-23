import KeyIcon from "@mui/icons-material/Key";
import RefreshIcon from "@mui/icons-material/Refresh";
import SaveIcon from "@mui/icons-material/Save";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import {
  type SettingsValues,
  useChangePassword,
  useQueues,
  useRefreshQueues,
  useRetryLogin,
  useSaveSettings,
  useSettings,
  useStatus,
} from "../../api/hooks";
import { minutesAgo } from "../../format";

const RAVON_STATE_TEXT: Record<string, string> = {
  ok: "Login OK",
  login_failed: "Login failed",
  unreachable: "Ravon isn't answering",
  no_credentials: "No login details",
  page_format_changed: "Ravon's page changed",
  unknown: "Not checked yet",
};

function timeZones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  return intl.supportedValuesOf?.("timeZone") ?? ["America/Chicago", "America/Denver", "America/New_York"];
}

function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <Paper component="section" aria-label={title} sx={{ p: { xs: 2.5, md: 3 }, display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Typography variant="h2" sx={{ flexGrow: 1 }}>
          {title}
        </Typography>
        {aside}
      </Box>
      {children}
    </Paper>
  );
}

function StoreQueues({ selected, onChange }: { selected: string[]; onChange: (queues: string[]) => void }) {
  const { data } = useQueues(true);
  const refresh = useRefreshQueues();
  const known = data?.queues ?? [];
  const unknownSelected = selected.filter((value) => !known.some((q) => q.value === value));
  const toggle = (value: string, on: boolean) =>
    onChange(on ? [...selected, value] : selected.filter((v) => v !== value));
  return (
    <Section
      title="Store queues"
      aside={
        <Button
          size="small"
          startIcon={<RefreshIcon />}
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending || data?.refresh_requested}
        >
          {data?.refresh_requested ? "Refreshing…" : "Refresh list"}
        </Button>
      }
    >
      <Typography color="text.secondary">
        Calls on these Ravon queues are collected. A queue you add lists its last 7 days without transcribing them.
        {data?.fetched_at ? ` List read from Ravon ${minutesAgo(data.fetched_at)}.` : ""}
      </Typography>
      {known.length === 0 && (
        <Alert severity="info">
          The worker hasn't read Ravon's queue list yet. It does this when it starts and when Ravon is reachable.
        </Alert>
      )}
      <FormGroup sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" } }}>
        {known.map((queue) => (
          <FormControlLabel
            key={queue.value}
            control={
              <Checkbox checked={selected.includes(queue.value)} onChange={(e) => toggle(queue.value, e.target.checked)} />
            }
            label={queue.label}
          />
        ))}
        {unknownSelected.map((value) => (
          <FormControlLabel
            key={value}
            control={<Checkbox checked onChange={() => toggle(value, false)} />}
            label={`${value} (not in Ravon's list)`}
          />
        ))}
      </FormGroup>
    </Section>
  );
}

function RavonLogin() {
  const { data } = useStatus();
  const retry = useRetryLogin();
  const state = data?.ravon_state ?? "unknown";
  return (
    <Section
      title="Ravon login"
      aside={<Chip size="small" color={state === "ok" ? "success" : "warning"} label={RAVON_STATE_TEXT[state]} />}
    >
      <Typography>
        The username and password live in the .env file next to the compose file. They can't be seen or changed here.
      </Typography>
      {data?.ravon_error && <Alert severity="warning">{data.ravon_error}</Alert>}
      <Box>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => retry.mutate()} disabled={retry.isPending}>
          Retry login
        </Button>
        {retry.isSuccess && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            The worker will try again within a few seconds.
          </Typography>
        )}
      </Box>
    </Section>
  );
}

function AdminAccount() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useChangePassword();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    change.mutate(
      { current, new: next },
      {
        onSuccess: () => {
          setCurrent("");
          setNext("");
        },
      },
    );
  };
  return (
    <Section title="Admin account">
      <Typography color="text.secondary">Sessions last 12 hours. Changing the password signs out every other session.</Typography>
      <Box component="form" onSubmit={submit} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {change.error && <Alert severity="error">{change.error.message}</Alert>}
        {change.isSuccess && <Alert severity="success">Password changed.</Alert>}
        <TextField label="Current password" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        <TextField
          label="New password"
          type="password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          autoComplete="new-password"
          required
          helperText="At least 12 characters."
        />
        <Box>
          <Button type="submit" variant="outlined" startIcon={<KeyIcon />} disabled={change.isPending}>
            Change password
          </Button>
        </Box>
      </Box>
    </Section>
  );
}

export function Settings() {
  const settings = useSettings(true);
  const save = useSaveSettings();
  const [draft, setDraft] = useState<SettingsValues | null>(null);
  const [saved, setSaved] = useState(false);
  const zones = useMemo(timeZones, []);

  useEffect(() => {
    if (settings.data && draft === null) setDraft(settings.data.values);
  }, [settings.data, draft]);

  if (!draft) return null;
  const fieldError = (key: string) =>
    save.error instanceof ApiError && save.error.key === key ? save.error.message : undefined;
  const set = <K extends keyof SettingsValues>(key: K, value: SettingsValues[K]) =>
    setDraft({ ...draft, [key]: value });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(
      { store_queues: draft.store_queues, poll_interval_minutes: draft.poll_interval_minutes, time_zone: draft.time_zone },
      {
        onSuccess: (data) => {
          setDraft(data.values);
          setSaved(true);
        },
      },
    );
  };

  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "flex-start" }}>
      <Box component="form" onSubmit={submit} sx={{ flex: "999 1 560px", minWidth: 0, display: "flex", flexDirection: "column", gap: 3 }}>
        <Typography variant="h1">Settings</Typography>
        {save.error && !(save.error instanceof ApiError && save.error.key) && <Alert severity="error">{save.error.message}</Alert>}
        <StoreQueues selected={draft.store_queues} onChange={(queues) => set("store_queues", queues)} />
        {fieldError("store_queues") && <Alert severity="error">{fieldError("store_queues")}</Alert>}
        <Section title="Checking for new calls">
          <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, maxWidth: 640 }}>
            <TextField
              label="Check every (minutes)"
              type="number"
              value={draft.poll_interval_minutes}
              onChange={(e) => set("poll_interval_minutes", Number(e.target.value))}
              error={Boolean(fieldError("poll_interval_minutes"))}
              helperText={fieldError("poll_interval_minutes") ?? "1 to 30"}
              slotProps={{ htmlInput: { step: 1 } }}
            />
            <Autocomplete
              options={zones}
              value={draft.time_zone}
              disableClearable
              onChange={(_e, value) => set("time_zone", value)}
              renderInput={(params) => (
                <TextField {...params} label="Store time zone" error={Boolean(fieldError("time_zone"))} helperText={fieldError("time_zone") ?? " "} />
              )}
            />
          </Box>
        </Section>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Button type="submit" variant="contained" size="large" startIcon={<SaveIcon />} disabled={save.isPending}>
            Save settings
          </Button>
          <Typography variant="body2" color="text.secondary">
            Changes apply without a restart.
          </Typography>
        </Box>
      </Box>
      <Box sx={{ flex: "1 1 320px", display: "flex", flexDirection: "column", gap: 3 }}>
        <RavonLogin />
        <AdminAccount />
      </Box>
      <Snackbar open={saved} autoHideDuration={4000} onClose={() => setSaved(false)} message="Settings saved." />
    </Box>
  );
}
