import RefreshIcon from "@mui/icons-material/Refresh";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import { type InfiniteData, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { type CallList, keys, type Status, useCheckRavon } from "../api/hooks";
import { clockTime, minutesAgo } from "../format";

export const CHECK_POLL_MS = 2_000;
export const CHECK_GIVE_UP_MS = 60_000;

type Phase = "idle" | "checking" | "finished";

interface Props {
  status: Status | undefined;
  // The list on screen, to tell which calls the check found.
  listKey: readonly unknown[];
  ids: number[];
  // Whether the worker is transcribing a call, so the check waits for it.
  busy: boolean;
  onFound: (ids: number[]) => void;
}

// "Check Ravon now" (design D7): asks the worker to poll, then watches the last check time.
export function CheckRavon({ status, listKey, ids, busy, onFound }: Props) {
  const client = useQueryClient();
  const check = useCheckRavon();
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState("");
  const before = useRef<{ lastPoll: string | null; ids: Set<number> } | null>(null);
  const idsNow = useRef(ids);
  idsNow.current = ids;
  const statusNow = useRef(status);
  statusNow.current = status;
  const listKeyNow = useRef(listKey);
  listKeyNow.current = listKey;

  // While checking, read the status every couple of seconds instead of every ten.
  useEffect(() => {
    if (phase !== "checking") return undefined;
    const poll = setInterval(() => void client.refetchQueries({ queryKey: keys.status }), CHECK_POLL_MS);
    const giveUp = setTimeout(() => {
      const latest = statusNow.current;
      setPhase("finished");
      setResult(
        latest && latest.ravon_state !== "ok"
          ? `Couldn't check Ravon: ${latest.ravon_error ?? "it isn't answering"}.`
          : "Ravon didn't answer within a minute. The worker keeps trying.",
      );
    }, CHECK_GIVE_UP_MS);
    return () => {
      clearInterval(poll);
      clearTimeout(giveUp);
    };
  }, [phase, client]);

  // The check is done when the worker reports a newer successful poll.
  const lastPoll = status?.last_poll_ok ?? null;
  useEffect(() => {
    if (phase !== "checking" || !before.current || lastPoll === before.current.lastPoll) return;
    const seen = before.current.ids;
    void client.refetchQueries({ queryKey: keys.calls }).then(() => {
      // Read the refreshed list from the cache: this render's ids are from before the refetch.
      const list = client.getQueryData<InfiniteData<CallList>>(listKeyNow.current);
      const now = list?.pages.flatMap((page) => page.calls.map((c) => c.id)) ?? [];
      const found = now.filter((id) => !seen.has(id));
      onFound(found);
      setResult(found.length === 0 ? "No new calls." : `${found.length} new ${found.length === 1 ? "call" : "calls"} found.`);
      setPhase("finished");
    });
  }, [phase, lastPoll, client, onFound]);

  const stopped = status !== undefined && !status.worker_running;
  const checking = phase === "checking" || check.isPending;
  let label = "Check Ravon now";
  if (checking) label = busy ? "Waiting for the current call…" : "Checking Ravon…";

  let hint = phase === "finished" ? result : "";
  if (checking) hint = busy ? "The worker is transcribing a call and checks Ravon as soon as it's done." : "Looking for calls since the last check.";
  if (check.error) hint = check.error.message;
  if (stopped) hint = "The worker isn't running, so Ravon can't be checked.";

  const press = () => {
    setResult("");
    check.mutate(undefined, {
      onSuccess: (reply) => {
        before.current = { lastPoll: reply.last_poll_ok, ids: new Set(idsNow.current) };
        setPhase("checking");
      },
    });
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: { xs: "flex-start", sm: "flex-end" }, gap: 0.75 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Typography variant="body2" color="text.secondary">
          Last check{" "}
          <Box component="strong" sx={{ color: "text.primary", fontWeight: 500 }}>
            {clockTime(lastPoll)}
          </Box>{" "}
          ({minutesAgo(lastPoll)})
        </Typography>
        <Button
          variant="contained"
          onClick={press}
          disabled={checking || stopped}
          startIcon={checking ? <CircularProgress size={16} color="inherit" /> : <RefreshIcon />}
          sx={{ minHeight: 44 }}
        >
          {label}
        </Button>
      </Box>
      <Typography variant="body2" role="status" color="text.secondary" sx={{ minHeight: 20 }}>
        {hint}
      </Typography>
    </Box>
  );
}
