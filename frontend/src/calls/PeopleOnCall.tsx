import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import { type Attribution, type CallDetail, useClaim, useConfirm, usePeople, useReject } from "../api/hooks";
import { mss } from "../format";
import { PersonChip } from "./PersonChip";

const METHOD: Record<Attribution["method"], string> = {
  name: "By name",
  manual: "Set by hand",
};

// Why the call is theirs: the words heard and when.
export function evidence(a: Attribution): string {
  const parts = [METHOD[a.method]];
  if (a.name_heard !== null) {
    parts.push(`heard "${a.name_heard}"${a.name_at_s !== null ? ` at ${mss(a.name_at_s)}` : ""}`);
  }
  return parts.join(" · ");
}

// Anyone on the shop network can claim, reject and confirm; no admin login is needed.
export function PeopleOnCall({ call }: { call: CallDetail }) {
  const people = usePeople();
  const claim = useClaim();
  const reject = useReject();
  const confirm = useConfirm();
  const [adding, setAdding] = useState<number | "">("");
  const busy = claim.isPending || reject.isPending || confirm.isPending;
  const error = claim.error ?? reject.error ?? confirm.error;
  const onCall = new Set(call.attributions.map((a) => a.profile_id));
  const others = (people.data?.people ?? []).filter((p) => !onCall.has(p.id));
  if (!people.data || (people.data.people.length === 0 && call.attributions.length === 0)) return null;

  return (
    <Paper component="section" aria-label="People on this call" sx={{ p: { xs: 2, md: 3 }, display: "flex", flexDirection: "column", gap: 1.5 }}>
      <Typography variant="h2">People on this call</Typography>
      {call.attributions.length === 0 && <Typography color="text.secondary">Nobody is matched to this call yet.</Typography>}
      {call.attributions.map((a) => (
        <Box key={a.profile_id} sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.5 }}>
          <PersonChip attribution={a} size="medium" />
          <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
            {a.status === "maybe" ? "Maybe · " : ""}
            {evidence(a)}
          </Typography>
          {a.status === "maybe" && (
            <Button size="small" variant="outlined" disabled={busy} onClick={() => confirm.mutate({ call: call.id, person: a.profile_id })}>
              Confirm {a.display_name}
            </Button>
          )}
          <Button size="small" disabled={busy} onClick={() => reject.mutate({ call: call.id, person: a.profile_id })}>
            Not {a.display_name}
          </Button>
        </Box>
      ))}
      {others.length > 0 && (
        <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.5, borderTop: 1, borderColor: "divider", pt: 1.5 }}>
          <TextField
            select
            size="small"
            label="Add a person"
            value={adding}
            onChange={(e) => setAdding(Number(e.target.value))}
            sx={{ minWidth: 200 }}
          >
            {others.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {p.display_name}
              </MenuItem>
            ))}
          </TextField>
          <Button
            variant="outlined"
            disabled={adding === "" || busy}
            onClick={() => adding !== "" && claim.mutate({ call: call.id, person: adding }, { onSuccess: () => setAdding("") })}
          >
            Add
          </Button>
        </Box>
      )}
      {error && <Alert severity="error">{error.message}</Alert>}
    </Paper>
  );
}
