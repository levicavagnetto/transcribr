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
  type SettingField,
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
import { monoFontFamily } from "../../theme";

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

function outOfBounds(field: SettingField | undefined, value: number): boolean {
  if (!field) return false;
  return (field.minimum !== undefined && value < field.minimum) || (field.maximum !== undefined && value > field.maximum);
}

// Digits only, without leading zeros: a type="number" input keeps "02" on screen because React
// leaves it alone while its number matches. Empty shows as empty and saves as 0, which is out of bounds.
// The limits come from the server's field list and are checked on leaving the field; the server checks again on save.
function MinutesField({
  field,
  value,
  onChange,
  error,
}: {
  field: SettingField | undefined;
  value: number;
  onChange: (minutes: number) => void;
  error?: string;
}) {
  const [text, setText] = useState(String(value));
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    setText((current) => (Number(current) === value ? current : String(value)));
  }, [value]);
  const localError = checked && outOfBounds(field, value) ? field?.message : undefined;
  const shown = localError ?? error;
  const hint = field?.minimum !== undefined && field.maximum !== undefined ? `${field.minimum} to ${field.maximum}` : " ";
  return (
    <TextField
      label="Check every (minutes)"
      value={text}
      onChange={(e) => {
        const digits = e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
        setText(digits);
        onChange(digits === "" ? 0 : Number(digits));
      }}
      onBlur={() => setChecked(true)}
      error={Boolean(shown)}
      helperText={shown ?? hint}
      slotProps={{ htmlInput: { inputMode: "numeric" } }}
    />
  );
}

function ResearchPrompt({ field, saved }: { field: SettingField | undefined; saved: string }) {
  const save = useSaveSettings();
  const [draft, setDraft] = useState(saved);
  const [tried, setTried] = useState(false);
  const [done, setDone] = useState(false);
  const max = field?.max_length ?? 4000;
  const empty = draft.trim().length === 0;
  const tooLong = draft.length > max;
  const serverError = save.error instanceof ApiError && save.error.key === "research_prompt" ? save.error.message : undefined;
  let error: string | undefined;
  if (tried && empty) error = "The prompt can't be empty. The previous prompt is still in use.";
  if (tooLong) error = `Use ${max.toLocaleString("en-US")} characters or fewer.`;
  error ??= serverError;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (empty || tooLong) return;
    save.mutate({ research_prompt: draft }, { onSuccess: () => setDone(true) });
  };
  const fallback = typeof field?.default === "string" ? field.default : undefined;

  return (
    <Box component="form" onSubmit={submit} noValidate>
      <Section title="Research prompt">
        <Typography color="text.secondary">
          Copy for ChatGPT puts this text first, then the call's date, time and length, then the transcript. Write it the
          way you'd ask ChatGPT yourself.
        </Typography>
        <TextField
          label="Prompt"
          multiline
          minRows={5}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setTried(false);
          }}
          error={Boolean(error)}
          helperText={error ?? `Between 1 and ${max.toLocaleString("en-US")} characters.`}
        />
        <Box sx={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 1.5 }}>
          <Typography variant="body2" color="text.secondary" sx={{ fontFamily: monoFontFamily }}>
            {draft.length.toLocaleString("en-US")} / {max.toLocaleString("en-US")}
          </Typography>
          <Box sx={{ display: "flex", gap: 1.5 }}>
            {fallback !== undefined && (
              <Button
                variant="outlined"
                onClick={() => {
                  setDraft(fallback);
                  setTried(false);
                }}
              >
                Reset to the default
              </Button>
            )}
            <Button type="submit" variant="contained" startIcon={<SaveIcon />} disabled={save.isPending}>
              Save prompt
            </Button>
          </Box>
        </Box>
      </Section>
      <Snackbar open={done} autoHideDuration={4000} onClose={() => setDone(false)} message="Research prompt saved." />
    </Box>
  );
}

const LOW = "voice_threshold_low";
const HIGH = "voice_threshold_high";

// Saved on its own: changing a threshold re-matches every transcribed call in the background.
function VoiceThresholds({ fields, values }: { fields: SettingField[]; values: SettingsValues }) {
  const save = useSaveSettings();
  const [low, setLow] = useState(String(values[LOW] ?? ""));
  const [high, setHigh] = useState(String(values[HIGH] ?? ""));
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const field = (key: string) => fields.find((f) => f.key === key);
  const serverError = save.error instanceof ApiError && (save.error.key === LOW || save.error.key === HIGH) ? save.error.message : null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const lowValue = Number(low);
    const highValue = Number(high);
    const inRange = (v: number, text: string) => text.trim() !== "" && Number.isFinite(v) && v >= 0 && v <= 1;
    if (!inRange(lowValue, low) || !inRange(highValue, high)) {
      setError(field(LOW)?.message ?? "Each voice threshold must be a number from 0 to 1.");
      return;
    }
    if (lowValue >= highValue) {
      setError("The weak voice match threshold must be below the strong one. The previous values are still in use.");
      return;
    }
    setError(null);
    save.mutate({ [LOW]: lowValue, [HIGH]: highValue }, { onSuccess: () => setDone(true) });
  };
  const shown = error ?? serverError;

  return (
    <Box component="form" onSubmit={submit} noValidate>
      <Section title="Voice matching">
        <Typography color="text.secondary">
          A call's voice presence score at or above the strong value counts as that person; between the weak and strong
          values it is a Maybe. Changing these re-matches every transcribed call.
        </Typography>
        <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, maxWidth: 640 }}>
          <TextField
            label={field(LOW)?.label ?? "Weak voice match from"}
            value={low}
            onChange={(e) => setLow(e.target.value)}
            helperText="0 to 1"
            error={Boolean(shown)}
            slotProps={{ htmlInput: { inputMode: "decimal" } }}
          />
          <TextField
            label={field(HIGH)?.label ?? "Strong voice match from"}
            value={high}
            onChange={(e) => setHigh(e.target.value)}
            helperText="0 to 1"
            error={Boolean(shown)}
            slotProps={{ htmlInput: { inputMode: "decimal" } }}
          />
        </Box>
        {shown && <Alert severity="error">{shown}</Alert>}
        <Box>
          <Button type="submit" variant="contained" startIcon={<SaveIcon />} disabled={save.isPending}>
            Save voice matching
          </Button>
        </Box>
      </Section>
      <Snackbar open={done} autoHideDuration={4000} onClose={() => setDone(false)} message="Voice matching saved. Calls are being re-matched." />
    </Box>
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
      <Box sx={{ flex: "999 1 560px", minWidth: 0, display: "flex", flexDirection: "column", gap: 3 }}>
        <Box component="form" onSubmit={submit} sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <Typography variant="h1">Settings</Typography>
          {save.error && !(save.error instanceof ApiError && save.error.key) && <Alert severity="error">{save.error.message}</Alert>}
          <StoreQueues selected={draft.store_queues} onChange={(queues) => set("store_queues", queues)} />
          {fieldError("store_queues") && <Alert severity="error">{fieldError("store_queues")}</Alert>}
          <Section title="Checking for new calls">
            <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, maxWidth: 640 }}>
              <MinutesField
                field={settings.data?.fields.find((f) => f.key === "poll_interval_minutes")}
                value={draft.poll_interval_minutes}
                onChange={(minutes) => set("poll_interval_minutes", minutes)}
                error={fieldError("poll_interval_minutes")}
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
        <ResearchPrompt
          field={settings.data?.fields.find((f) => f.key === "research_prompt")}
          saved={settings.data?.values.research_prompt ?? ""}
        />
        {settings.data && <VoiceThresholds fields={settings.data.fields} values={settings.data.values} />}
      </Box>
      <Box sx={{ flex: "1 1 320px", display: "flex", flexDirection: "column", gap: 3 }}>
        <RavonLogin />
        <AdminAccount />
      </Box>
      <Snackbar open={saved} autoHideDuration={4000} onClose={() => setSaved(false)} message="Settings saved." />
    </Box>
  );
}
