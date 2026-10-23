import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router";

import { useStatus } from "../api/hooks";
import { clockTime, minutesAgo } from "../format";
import { monoFontFamily } from "../theme";

function Figure({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Paper sx={{ p: 2.5, display: "flex", flexDirection: "column", gap: 0.5 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h2" component="p" sx={{ fontSize: 36, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Typography>
      {hint && (
        <Typography variant="caption" color="text.secondary" sx={{ fontFamily: monoFontFamily }}>
          {hint}
        </Typography>
      )}
    </Paper>
  );
}

// The collection status. add-call-browser replaces this page with the call list.
export function Home() {
  const { data, isLoading, error } = useStatus();
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Typography variant="h1">Calls collected</Typography>
      {error && <Alert severity="error">{error.message}</Alert>}
      {data && !data.admin_exists && (
        <Alert severity="info">
          First-time setup: follow the{" "}
          <Link component={RouterLink} to="/admin">
            Admin
          </Link>{" "}
          link and enter the setup code from the server log.
        </Alert>
      )}
      {data && data.admin_exists && !data.queues_chosen && (
        <Alert severity="info">
          No store queues are chosen yet, so no calls are being collected. The admin can choose them
          at{" "}
          <Link component={RouterLink} to="/admin/settings">
            /admin/settings
          </Link>
          .
        </Alert>
      )}
      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(5, minmax(0, 1fr))" },
        }}
      >
        {isLoading &&
          Array.from({ length: 5 }, (_, i) => <Skeleton key={i} variant="rounded" height={120} />)}
        {data && (
          <>
            <Figure
              label="Last check"
              value={clockTime(data.last_poll_ok)}
              hint={minutesAgo(data.last_poll_ok)}
            />
            <Figure label="Listed today" value={data.listed_today} />
            <Figure label="Transcribed today" value={data.transcribed_today} />
            <Figure label="Waiting" value={data.waiting} hint="queued or transcribing now" />
            <Figure label="Failed" value={data.failed_last_24h} hint="in the last 24 hours" />
          </>
        )}
      </Box>
    </Box>
  );
}
