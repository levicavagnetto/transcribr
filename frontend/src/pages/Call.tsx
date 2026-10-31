import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { type ReactNode, useState } from "react";
import { Link as RouterLink, useParams } from "react-router";

import { API } from "../api/client";
import {
  type CallDetail,
  type Transcript,
  useAuthState,
  useCall,
  useEnroll,
  usePeople,
  useResearchPrompt,
  useTranscribe,
  useTranscript,
} from "../api/hooks";
import { CopyForChatGpt } from "../calls/CopyForChatGpt";
import { PeopleOnCall } from "../calls/PeopleOnCall";
import { StateChip } from "../calls/StateChip";
import { clockTime, fullDate, longLength, mss, startLabel } from "../format";
import { monoFontFamily } from "../theme";

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box>
      <Typography component="dt" variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
        {label}
      </Typography>
      <Typography component="dd" sx={{ m: 0, mt: 0.5 }}>
        {children}
      </Typography>
    </Box>
  );
}

function howTranscribed(call: CallDetail): string {
  if (!call.transcribed_at) return call.state === "transcribed" ? "Yes" : "Not yet";
  return `${call.auto_queued ? "Automatically" : "On request"}, ${clockTime(call.transcribed_at)}`;
}

// What can be done with the call in its current state.
function Actions({ call, transcript }: { call: CallDetail; transcript: Transcript | undefined }) {
  const transcribe = useTranscribe();
  const prompt = useResearchPrompt();
  if (call.state === "transcribed" && call.no_speech) {
    return <Typography>The recording had no recognizable speech, perhaps a hang-up or hold music.</Typography>;
  }
  if (call.state === "transcribed") {
    if (!transcript || !prompt.data) return <Skeleton variant="rounded" height={44} width={220} />;
    return <CopyForChatGpt call={call} segments={transcript.segments} prompt={prompt.data.prompt} />;
  }
  if (call.state === "not_transcribed") {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 1.5 }}>
        <Typography>This call ended while Transcribr was off, so it wasn't transcribed automatically.</Typography>
        <Button variant="contained" onClick={() => transcribe.mutate(call.id)} disabled={transcribe.isPending}>
          Transcribe
        </Button>
      </Box>
    );
  }
  if (call.state === "failed") {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 1.5 }}>
        <Alert severity="error" sx={{ alignSelf: "stretch" }}>
          <strong>Transcription failed.</strong> {call.failure_reason ?? "No reason was recorded."}
        </Alert>
        <Button variant="contained" onClick={() => transcribe.mutate(call.id)} disabled={transcribe.isPending}>
          Retry
        </Button>
      </Box>
    );
  }
  return (
    <Alert severity="info">
      {call.state === "processing" ? "Transcribing… " : "Waiting to be transcribed. "}
      The transcript appears here when it's done.
    </Alert>
  );
}

function Listen({ call }: { call: CallDetail }) {
  const [failed, setFailed] = useState(false);
  return (
    <Paper component="section" aria-label="Listen" sx={{ p: { xs: 2, md: 3 }, display: "flex", flexDirection: "column", gap: 1.5 }}>
      <Typography variant="body2" color="text.secondary">
        Listen (streamed from Ravon, not saved)
      </Typography>
      <Box
        component="audio"
        controls
        preload="none"
        src={`${API}/calls/${call.id}/audio`}
        onError={() => setFailed(true)}
        onPlay={() => setFailed(false)}
        sx={{ width: "100%", colorScheme: "light dark" }}
      />
      {failed && <Alert severity="error">The recording can't be fetched from Ravon right now. Try again in a minute.</Alert>}
    </Paper>
  );
}

const NO_VOICEPRINT = "Can't be enrolled: under 1 second, or transcribed before voiceprints were kept.";

// The admin ticks lines where only one person talks and enrolls them for that person's voice profile.
function EnrollBar({ callId, ticked, onDone }: { callId: number; ticked: number[]; onDone: () => void }) {
  const people = usePeople();
  const enroll = useEnroll();
  const [person, setPerson] = useState<number | "">("");
  const [done, setDone] = useState<string | null>(null);
  const list = people.data?.people ?? [];
  const chosen = list.find((p) => p.id === person);
  if (list.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Add people in Admin, People to enroll their voice from these lines.
      </Typography>
    );
  }
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.5, mb: 1.5 }}>
      <Typography variant="body2" color="text.secondary">
        Tick lines where only one person is talking. {ticked.length} ticked.
      </Typography>
      <TextField select size="small" label="Person" value={person} onChange={(e) => setPerson(Number(e.target.value))} sx={{ minWidth: 180 }}>
        {list.map((p) => (
          <MenuItem key={p.id} value={p.id}>
            {p.display_name}
          </MenuItem>
        ))}
      </TextField>
      <Button
        variant="contained"
        disabled={!chosen || ticked.length === 0 || enroll.isPending}
        onClick={() =>
          chosen &&
          enroll.mutate(
            { person: chosen.id, call: callId, lines: ticked },
            {
              onSuccess: () => {
                setDone(`Enrolled ${ticked.length} ${ticked.length === 1 ? "line" : "lines"} for ${chosen.display_name}.`);
                onDone();
              },
            },
          )
        }
      >
        Enroll as {chosen?.display_name ?? "…"}
      </Button>
      {done && <Alert severity="success">{done}</Alert>}
      {enroll.error && <Alert severity="error">{enroll.error.message}</Alert>}
    </Box>
  );
}

function TranscriptView({ transcript, canEnroll }: { transcript: Transcript; canEnroll: boolean }) {
  const [ticked, setTicked] = useState<number[]>([]);
  const toggle = (idx: number, on: boolean) =>
    setTicked((current) => (on ? [...current, idx].sort((a, b) => a - b) : current.filter((i) => i !== idx)));
  const columns = canEnroll ? "40px 48px minmax(0, 1fr)" : "48px minmax(0, 1fr)";
  return (
    <Paper component="section" aria-label="Transcript" sx={{ p: { xs: 2, md: 3 } }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: 1, mb: 1 }}>
        <Typography variant="h2">Transcript</Typography>
        <Typography variant="body2" color="text.secondary">
          {transcript.segments.length} {transcript.segments.length === 1 ? "line" : "lines"} · {transcript.model}
        </Typography>
      </Box>
      {canEnroll && <EnrollBar callId={transcript.call_id} ticked={ticked} onDone={() => setTicked([])} />}
      {transcript.segments.map((segment) => (
        <Box
          key={segment.idx}
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: columns, sm: canEnroll ? "40px 56px minmax(0, 1fr)" : "56px minmax(0, 1fr)" },
            columnGap: 1.5,
            alignItems: "start",
            py: 1,
            borderTop: 1,
            borderColor: "divider",
            lineHeight: 1.5,
          }}
        >
          {canEnroll && (
            <Checkbox
              size="small"
              sx={{ p: 0.25 }}
              checked={ticked.includes(segment.idx)}
              disabled={!segment.has_voiceprint}
              onChange={(e) => toggle(segment.idx, e.target.checked)}
              title={segment.has_voiceprint ? undefined : NO_VOICEPRINT}
              slotProps={{
                input: {
                  "aria-label": segment.has_voiceprint
                    ? `Line at ${mss(segment.start_s)}`
                    : `Line at ${mss(segment.start_s)}. ${NO_VOICEPRINT}`,
                },
              }}
            />
          )}
          <Typography component="span" variant="body2" color="text.secondary" sx={{ fontFamily: monoFontFamily, pt: 0.25 }}>
            {mss(segment.start_s)}
          </Typography>
          <Typography component="span">{segment.text}</Typography>
        </Box>
      ))}
    </Paper>
  );
}

export function Call() {
  const id = Number(useParams().id);
  const call = useCall(id);
  const transcript = useTranscript(id, call.data?.has_transcript === true && !call.data.no_speech);
  const isAdmin = useAuthState().data?.state === "logged_in";

  const back = (
    <Link component={RouterLink} to="/" sx={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 0.5, fontWeight: 500, py: 1 }}>
      <ArrowBackIcon fontSize="small" />
      All calls
    </Link>
  );
  if (call.error) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {back}
        <Alert severity="error">{call.error.message}</Alert>
      </Box>
    );
  }
  const data = call.data;
  return (
    <Box sx={{ maxWidth: 1040, width: "100%", mx: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
      {back}
      {!data && <Skeleton variant="rounded" height={220} />}
      {data && (
        <>
          <Paper component="section" aria-label="Call details" sx={{ p: { xs: 2, md: 3 }, display: "flex", flexDirection: "column", gap: 2 }}>
            <Box sx={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-start", gap: 1.5 }}>
              <Box>
                <Typography variant="h1">
                  {startLabel(data.start_local)} · {longLength(data.minutes)}
                </Typography>
                <Typography color="text.secondary">{fullDate(data.start_local)}</Typography>
              </Box>
              <StateChip state={data.state} />
            </Box>
            <Box component="dl" sx={{ m: 0, display: "grid", gap: "12px 24px", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
              <Detail label="Caller">
                <Box component="span" sx={{ fontFamily: monoFontFamily }}>
                  {data.caller_number}
                </Box>
              </Detail>
              <Detail label="Answered by">{data.answered_by}</Detail>
              <Detail label="Queue">{data.queue_label ?? data.queue}</Detail>
              <Detail label="Transcribed">{howTranscribed(data)}</Detail>
            </Box>
            <Box sx={{ borderTop: 1, borderColor: "divider", pt: 2 }}>
              <Actions call={data} transcript={transcript.data} />
            </Box>
          </Paper>
          {data.state === "transcribed" && <PeopleOnCall call={data} />}
          <Listen call={data} />
          {transcript.data && transcript.data.segments.length > 0 && (
            <TranscriptView transcript={transcript.data} canEnroll={isAdmin} />
          )}
        </>
      )}
    </Box>
  );
}
