import SearchIcon from "@mui/icons-material/Search";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import InputAdornment from "@mui/material/InputAdornment";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link as RouterLink } from "react-router";

import {
  type CallFilters,
  type CallListItem,
  type CallState,
  keys,
  useCalls,
  useLoadEarlier,
  useStatus,
  useTranscribe,
} from "../api/hooks";
import { CheckRavon } from "../calls/CheckRavon";
import { STATE_LABEL, StateChip } from "../calls/StateChip";
import { mss, startLabel } from "../format";
import { monoFontFamily } from "../theme";

export const SEARCH_DELAY_MS = 300;

const STATES: (CallState | "any")[] = ["any", "transcribed", "waiting", "processing", "not_transcribed", "failed"];

// Words go to text search; something that is only a phone number (3+ digits, no letters) to number search.
export function searchFilter(text: string): Pick<CallFilters, "q" | "number"> {
  const trimmed = text.trim();
  if (!trimmed) return {};
  if (/[a-z]/i.test(trimmed)) return { q: trimmed };
  return trimmed.replace(/\D/g, "").length >= 3 ? { number: trimmed } : {};
}

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

function Notes({ call, isNew }: { call: CallListItem; isNew: boolean }) {
  const transcribe = useTranscribe();
  return (
    <Box sx={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 1.5, color: "text.secondary" }}>
      {isNew && (
        <Typography variant="body2" sx={{ color: "text.primary", fontWeight: 500 }}>
          New
        </Typography>
      )}
      {call.no_speech && <Typography variant="body2">No speech</Typography>}
      {call.state === "not_transcribed" && (
        <>
          <Typography variant="body2">Ended while Transcribr was off</Typography>
          <Button
            variant="outlined"
            size="small"
            disabled={transcribe.isPending}
            onClick={() => transcribe.mutate(call.id)}
            aria-label={`Transcribe the call from ${startLabel(call.start_local)}`}
          >
            Transcribe
          </Button>
        </>
      )}
    </Box>
  );
}

function Passage({ call }: { call: CallListItem }) {
  if (!call.passage) return null;
  return (
    <TableRow>
      <TableCell colSpan={6} sx={{ pt: 0, pb: 1.5, pl: { xs: 2, md: 22 }, color: "text.secondary", lineHeight: 1.6 }}>
        <Box component="span" sx={{ fontFamily: monoFontFamily, fontSize: 12, mr: 1 }}>
          at {mss(call.passage.at_s)}
        </Box>
        “
        {call.passage.parts.map((part, i) =>
          part.hit ? (
            <Box
              key={i}
              component="mark"
              sx={{ bgcolor: "highlight.background", color: "highlight.text", borderRadius: 0.5, px: 0.25 }}
            >
              {part.text}
            </Box>
          ) : (
            <Fragment key={i}>{part.text}</Fragment>
          ),
        )}
        ”
      </TableCell>
    </TableRow>
  );
}

function SetupNotice() {
  const { data } = useStatus();
  if (data && !data.admin_exists) {
    return (
      <Alert severity="info">
        First-time setup: follow the{" "}
        <Link component={RouterLink} to="/admin">
          Admin
        </Link>{" "}
        link and enter the setup code from the server log.
      </Alert>
    );
  }
  if (data && !data.queues_chosen) {
    return (
      <Alert severity="info">
        No store queues are chosen yet, so no calls are being collected. The admin can choose them at{" "}
        <Link component={RouterLink} to="/admin/settings">
          /admin/settings
        </Link>
        .
      </Alert>
    );
  }
  return null;
}

export function Calls() {
  const status = useStatus();
  const [text, setText] = useState("");
  const [state, setState] = useState<CallState | "any">("any");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const search = useDebounced(text, SEARCH_DELAY_MS);
  const filters = useMemo<CallFilters>(
    () => ({
      ...searchFilter(search),
      ...(state === "any" ? {} : { state }),
      ...(from ? { from } : {}),
      ...(to ? { to } : {}),
    }),
    [search, state, from, to],
  );
  const filtered = Object.keys(filters).length > 0;
  const calls = useCalls(filters);
  const rows = useMemo(() => calls.data?.pages.flatMap((page) => page.calls) ?? [], [calls.data]);
  const [newIds, setNewIds] = useState<Set<number>>(new Set());
  const onFound = useCallback((ids: number[]) => setNewIds(new Set(ids)), []);
  const loadEarlier = useLoadEarlier();

  // Older calls load as the end of the list scrolls into view (the button does the same).
  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = calls;
  useEffect(() => {
    const target = sentinel.current;
    if (!target || typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting) && hasNextPage && !isFetchingNextPage) void fetchNextPage();
    });
    observer.observe(target);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const clear = () => {
    setText("");
    setState("any");
    setFrom("");
    setTo("");
  };
  const count = `${rows.length}${hasNextPage ? "+" : ""}`;
  const summary = filtered
    ? `${count} ${rows.length === 1 && !hasNextPage ? "call matches" : "calls match"}`
    : "Newest first";
  const oldest = rows.at(-1);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-end", gap: 2 }}>
        <Box>
          <Typography variant="h1">Calls</Typography>
          <Typography color="text.secondary">Open a call to read, listen or copy it for ChatGPT.</Typography>
        </Box>
        <CheckRavon
          status={status.data}
          listKey={keys.callList(filters)}
          ids={rows.map((r) => r.id)}
          busy={rows.some((r) => r.state === "processing")}
          onFound={onFound}
        />
      </Box>

      <SetupNotice />

      <Paper component="section" aria-label="Find calls" sx={{ p: 2, display: "flex", flexWrap: "wrap", gap: 2, alignItems: "flex-end" }}>
        <TextField
          label="Search words said, or a phone number"
          placeholder="Try: lift kit, Silverado, or 555 0142"
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          sx={{ flex: "3 1 280px" }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
            },
          }}
        />
        <Box sx={{ flex: "4 1 420px", display: "flex", flexDirection: "column", gap: 0.75 }}>
          <Typography id="state-filter-label" variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
            State
          </Typography>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={state}
            onChange={(_e, value: CallState | "any" | null) => value && setState(value)}
            aria-labelledby="state-filter-label"
            sx={{ flexWrap: "wrap", gap: 0.75, "& .MuiToggleButton-root": { borderRadius: "16px !important", border: 1, px: 1.75 } }}
          >
            {STATES.map((value) => (
              <ToggleButton key={value} value={value}>
                {value === "any" ? "Any" : STATE_LABEL[value]}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Box>
        <Box sx={{ flex: "2 1 280px", display: "flex", gap: 1.5 }}>
          <TextField label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} sx={{ flex: 1 }} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} sx={{ flex: 1 }} slotProps={{ inputLabel: { shrink: true } }} />
        </Box>
      </Paper>

      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 1 }}>
        <Typography color="text.secondary">{summary}</Typography>
        {filtered && <Button onClick={clear}>Clear search and filters</Button>}
      </Box>

      {calls.error && <Alert severity="error">{calls.error.message}</Alert>}

      <TableContainer component={Paper} aria-label="Calls">
        <Table size="small" sx={{ minWidth: 920 }}>
          <TableHead>
            <TableRow>
              <TableCell>Started</TableCell>
              <TableCell>Length</TableCell>
              <TableCell>Caller</TableCell>
              <TableCell>Answered by</TableCell>
              <TableCell>State</TableCell>
              <TableCell>
                <Box component="span" sx={visuallyHidden}>
                  Notes
                </Box>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {calls.isLoading &&
              Array.from({ length: 6 }, (_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={6}>
                    <Skeleton />
                  </TableCell>
                </TableRow>
              ))}
            {rows.map((call) => {
              const isNew = newIds.has(call.id);
              return (
                <Fragment key={call.id}>
                  <TableRow
                    sx={{
                      bgcolor: isNew ? "attribution.maybeBg" : undefined,
                      "& > td": call.passage ? { borderBottom: 0 } : {},
                    }}
                  >
                    <TableCell>
                      <Link component={RouterLink} to={`/calls/${call.id}`} sx={{ fontWeight: 500, py: 1, display: "inline-block" }}>
                        {startLabel(call.start_local)}
                      </Link>
                    </TableCell>
                    <TableCell sx={{ fontFamily: monoFontFamily }}>{mss(call.minutes * 60)}</TableCell>
                    <TableCell sx={{ fontFamily: monoFontFamily }}>{call.caller_number}</TableCell>
                    <TableCell sx={{ color: "text.secondary" }}>{call.answered_by}</TableCell>
                    <TableCell>
                      <StateChip state={call.state} />
                    </TableCell>
                    <TableCell>
                      <Notes call={call} isNew={isNew} />
                    </TableCell>
                  </TableRow>
                  <Passage call={call} />
                </Fragment>
              );
            })}
            {!calls.isLoading && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} sx={{ py: 6, textAlign: "center", color: "text.secondary" }}>
                  {filtered ? (
                    <>
                      <Typography sx={{ fontWeight: 500, color: "text.primary" }}>No calls match</Typography>
                      Try fewer words, a different date range, or clear the state filter.
                    </>
                  ) : (
                    "No calls are listed yet."
                  )}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        <Box
          ref={sentinel}
          sx={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 1.5, px: 2, py: 1.5, color: "text.secondary" }}
        >
          {hasNextPage && (
            <Button onClick={() => void fetchNextPage()} disabled={isFetchingNextPage}>
              {isFetchingNextPage ? "Loading older calls…" : "Show older calls"}
            </Button>
          )}
          {!hasNextPage && !filtered && oldest && (
            <>
              <Typography variant="body2">
                {loadEarlier.isSuccess
                  ? "Asked the worker to list the week before. Those calls appear here within a minute or two."
                  : `That's everything listed. The oldest is from ${startLabel(oldest.start_local)}.`}
              </Typography>
              <Button variant="outlined" onClick={() => loadEarlier.mutate()} disabled={loadEarlier.isPending || loadEarlier.isSuccess}>
                List the week before from Ravon
              </Button>
            </>
          )}
        </Box>
      </TableContainer>
    </Box>
  );
}

const visuallyHidden = {
  position: "absolute",
  width: 1,
  height: 1,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
} as const;
