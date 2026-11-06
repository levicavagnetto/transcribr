import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";

import type { Status } from "../api/hooks";
import { useRetryLogin } from "../api/hooks";
import { minutesAgo } from "../format";

export interface Problem {
  id: string;
  severity: "error" | "warning";
  title: string;
  text: string;
  retryLogin?: boolean;
}

// Plain-language problems that need someone's attention, most serious first.
export function problemsFrom(status: Status): Problem[] {
  const problems: Problem[] = [];
  if (status.ravon_state === "no_credentials") {
    problems.push({
      id: "no_credentials",
      severity: "error",
      title: "Ravon login details are missing.",
      text: "Set RAVON_USERNAME and RAVON_PASSWORD in the .env file next to the compose file, then restart Transcribr.",
    });
  }
  if (status.ravon_state === "login_failed") {
    problems.push({
      id: "login_failed",
      severity: "error",
      title: "Ravon login failed.",
      text: "New calls aren't being collected. Check RAVON_USERNAME and RAVON_PASSWORD in the .env file and restart, or retry if the password was just changed in Ravon.",
      retryLogin: true,
    });
  }
  if (status.ravon_state === "page_format_changed") {
    problems.push({
      id: "page_format_changed",
      severity: "error",
      title: "Ravon's recordings page has changed.",
      text: "Transcribr can't read the call list any more and has stopped collecting calls. It needs an update.",
    });
  }
  if (!status.worker_running) {
    problems.push({
      id: "worker_stopped",
      severity: "error",
      title: status.worker_last_seen ? "The worker has stopped." : "The worker hasn't started yet.",
      text: status.worker_last_seen
        ? `Calls aren't being collected or transcribed. It was last seen ${minutesAgo(status.worker_last_seen)}. Check that the worker service is running.`
        : "Calls aren't being collected or transcribed yet. Check that the worker service is running.",
    });
  }
  if (status.ravon_state === "unreachable") {
    problems.push({
      id: "unreachable",
      severity: "warning",
      title: "Ravon isn't answering.",
      text: `Transcribr keeps trying and will catch up when Ravon is back. Last successful check: ${minutesAgo(status.last_poll_ok)}.`,
    });
  }
  if (status.guard_violations > 0) {
    problems.push({
      id: "guard_violations",
      severity: "warning",
      title: `${status.guard_violations} request(s) to Ravon were blocked.`,
      text: "Transcribr refused requests that aren't on its read-only list. Nothing was changed in Ravon, but this points to a bug worth reporting.",
    });
  }
  return problems;
}

export function StatusBanner({ status, isAdmin }: { status: Status | undefined; isAdmin: boolean }) {
  const retry = useRetryLogin();
  if (!status) return null;
  const problems = problemsFrom(status);
  if (problems.length === 0) return null;
  return (
    <Stack spacing={1} sx={{ maxWidth: 1400, mx: "auto", px: 3, pt: 2 }}>
      {problems.map((problem) => (
        <Alert
          key={problem.id}
          severity={problem.severity}
          role="alert"
          action={
            problem.retryLogin && isAdmin ? (
              <Button color="inherit" onClick={() => retry.mutate()} disabled={retry.isPending}>
                Retry login
              </Button>
            ) : undefined
          }
        >
          <AlertTitle>{problem.title}</AlertTitle>
          {problem.text}
        </Alert>
      ))}
    </Stack>
  );
}
