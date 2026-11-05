import AddIcon from "@mui/icons-material/Add";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { type FormEvent, useState } from "react";

import {
  type Profile,
  type ProfileIn,
  useCreateProfile,
  useDeleteProfile,
  useProfiles,
  useUpdateProfile,
} from "../../api/hooks";

// "Nolan, Nolen" -> ["Nolan", "Nolen"]; the display name's first word when nothing is listed.
function parseVariants(text: string, name: string): string[] {
  const listed = text.split(",").map((v) => v.trim()).filter(Boolean);
  if (listed.length > 0) return listed;
  const first = name.trim().split(/\s+/)[0];
  return first ? [first] : [];
}

function ProfileForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
  pending,
  error,
}: {
  initial?: ProfileIn;
  submitLabel: string;
  onSubmit: (body: ProfileIn, reset: () => void) => void;
  onCancel?: () => void;
  pending: boolean;
  error?: string;
}) {
  const [name, setName] = useState(initial?.display_name ?? "");
  const [variants, setVariants] = useState(initial?.variants.join(", ") ?? "");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit({ display_name: name.trim(), variants: parseVariants(variants, name) }, () => {
      setName("");
      setVariants("");
    });
  };
  return (
    <Box component="form" onSubmit={submit} sx={{ display: "flex", flexWrap: "wrap", gap: 2, alignItems: "flex-start" }}>
      <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} required sx={{ flex: "1 1 200px" }} />
      <TextField
        label="Spellings in transcripts"
        value={variants}
        onChange={(e) => setVariants(e.target.value)}
        helperText="Separate with commas, e.g. Nolan, Nolen. Short names need each likely spelling."
        sx={{ flex: "2 1 320px" }}
      />
      <Box sx={{ display: "flex", gap: 1, pt: 1 }}>
        <Button type="submit" variant="contained" startIcon={initial ? undefined : <AddIcon />} disabled={pending}>
          {submitLabel}
        </Button>
        {onCancel && <Button onClick={onCancel}>Cancel</Button>}
      </Box>
      {error && (
        <Alert severity="error" sx={{ flexBasis: "100%" }}>
          {error}
        </Alert>
      )}
    </Box>
  );
}

function ProfileCard({ profile }: { profile: Profile }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const update = useUpdateProfile();
  const remove = useDeleteProfile();
  const f = profile.found;
  const found = [`${f.name} by name`, `${f.manual} by hand`, `${f.maybe} still Maybe`].join(" · ");
  return (
    <Paper component="section" aria-label={profile.display_name} sx={{ p: { xs: 2, md: 3 }, display: "flex", flexDirection: "column", gap: 1.5 }}>
      {editing ? (
        <ProfileForm
          initial={profile}
          submitLabel="Save"
          pending={update.isPending}
          error={update.error?.message}
          onCancel={() => setEditing(false)}
          onSubmit={(body) => update.mutate({ id: profile.id, ...body }, { onSuccess: () => setEditing(false) })}
        />
      ) : (
        <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1 }}>
          <Typography variant="h2" sx={{ mr: 1 }}>
            {profile.display_name}
          </Typography>
          {profile.variants.map((v) => (
            <Chip key={v} size="small" variant="outlined" label={v} />
          ))}
          <Box sx={{ flexGrow: 1 }} />
          <Button size="small" onClick={() => setEditing(true)}>
            Edit
          </Button>
          <Button size="small" color="error" onClick={() => setConfirming(true)}>
            Delete
          </Button>
        </Box>
      )}
      {confirming && (
        <Alert
          severity="warning"
          action={
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button color="inherit" size="small" onClick={() => setConfirming(false)}>
                Keep
              </Button>
              <Button color="error" size="small" variant="contained" disabled={remove.isPending} onClick={() => remove.mutate(profile.id)}>
                Delete {profile.display_name}
              </Button>
            </Box>
          }
        >
          This deletes {profile.display_name} and every call attribution to them.
        </Alert>
      )}
      <Typography variant="body2" color="text.secondary">
        How calls were found: {found}
      </Typography>
    </Paper>
  );
}

export function People() {
  const profiles = useProfiles();
  const create = useCreateProfile();
  const list = profiles.data?.profiles ?? [];
  return (
    <Box sx={{ maxWidth: 1040, display: "flex", flexDirection: "column", gap: 3 }}>
      <Box>
        <Typography variant="h1">People</Typography>
        <Typography color="text.secondary">
          The people who answer the phones. A call becomes a Maybe for someone when their name is heard in the first 30
          seconds. Confirm it, or mark it Not them, on the call's screen.
        </Typography>
      </Box>
      <Paper component="section" aria-label="Add a person" sx={{ p: { xs: 2, md: 3 }, display: "flex", flexDirection: "column", gap: 2 }}>
        <Typography variant="h2">Add a person</Typography>
        <ProfileForm
          submitLabel="Add"
          pending={create.isPending}
          error={create.error?.message}
          onSubmit={(body, reset) => create.mutate(body, { onSuccess: reset })}
        />
      </Paper>
      {profiles.error && <Alert severity="error">{profiles.error.message}</Alert>}
      {profiles.data && list.length === 0 && <Typography color="text.secondary">No people yet.</Typography>}
      {list.map((p) => (
        <ProfileCard key={p.id} profile={p} />
      ))}
    </Box>
  );
}
