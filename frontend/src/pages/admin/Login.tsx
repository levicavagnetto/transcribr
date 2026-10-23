import LoginIcon from "@mui/icons-material/Login";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";

import { useLogin } from "../../api/hooks";
import { monoFontFamily } from "../../theme";
import { AuthCard } from "./AuthCard";

export function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();
  const navigate = useNavigate();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate({ username, password }, { onSuccess: () => void navigate("/admin/settings") });
  };

  return (
    <AuthCard title="Admin sign in" intro="For managing settings. The rest of the app doesn't need a login.">
      <Box component="form" onSubmit={submit} sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
        {login.error && <Alert severity="error">{login.error.message}</Alert>}
        <TextField
          label="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
          autoFocus
        />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
        <Button type="submit" variant="contained" size="large" startIcon={<LoginIcon />} disabled={login.isPending}>
          Sign in
        </Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ pt: 2, borderTop: 1, borderColor: "divider" }}>
        Forgot the password? Whoever runs the server can reset it with{" "}
        <Box component="span" sx={{ fontFamily: monoFontFamily, color: "text.primary" }}>
          docker compose exec web transcribr reset-admin
        </Box>
        , which prints a new setup code.
      </Typography>
    </AuthCard>
  );
}
