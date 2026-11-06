import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";

import { ApiError } from "../../api/client";
import { useSetup } from "../../api/hooks";
import { monoFontFamily } from "../../theme";
import { AuthCard } from "./AuthCard";

const MIN_PASSWORD = 12;

export function Setup() {
  const [step, setStep] = useState<0 | 1>(0);
  const [code, setCode] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);
  const setup = useSetup();
  const navigate = useNavigate();

  const continueToAccount = (event: FormEvent) => {
    event.preventDefault();
    setCodeError(null);
    setStep(1);
  };

  const create = (event: FormEvent) => {
    event.preventDefault();
    setup.mutate(
      { code, username, password },
      {
        onSuccess: () => void navigate("/admin/settings"),
        onError: (error) => {
          if (error instanceof ApiError && error.code === "wrong_setup_code") {
            setCodeError(error.message);
            setStep(0);
          }
        },
      },
    );
  };

  const short = password.length > 0 && password.length < MIN_PASSWORD;
  const mismatch = repeat.length > 0 && repeat !== password;
  const otherError = setup.error && !(setup.error instanceof ApiError && setup.error.code === "wrong_setup_code");

  return (
    <AuthCard
      title="Set up the admin account"
      intro="There's no admin on this Transcribr yet. The admin manages settings; everyone else uses the app without logging in."
    >
      <Stepper activeStep={step} aria-label="Steps">
        <Step>
          <StepLabel>Setup code</StepLabel>
        </Step>
        <Step>
          <StepLabel>Admin account</StepLabel>
        </Step>
      </Stepper>

      {step === 0 ? (
        <Box component="form" onSubmit={continueToAccount} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {codeError && <Alert severity="error">{codeError}</Alert>}
          <Typography>
            To prove you run this server, enter the one-time setup code it printed in its log. Run this on the server:
          </Typography>
          <Box
            component="pre"
            sx={{ m: 0, p: 1.5, borderRadius: 2, bgcolor: "grey.900", color: "common.white", fontFamily: monoFontFamily, fontSize: 13, overflowX: "auto" }}
          >
            docker compose logs web | grep "setup code"
          </Box>
          <TextField
            label="Setup code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="XXXX-XXXX-XX"
            autoComplete="off"
            required
            autoFocus
            slotProps={{ htmlInput: { spellCheck: false, style: { fontFamily: monoFontFamily, letterSpacing: "0.08em" } } }}
          />
          <Button type="submit" variant="contained" size="large" endIcon={<ArrowForwardIcon />}>
            Continue
          </Button>
        </Box>
      ) : (
        <Box component="form" onSubmit={create} sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
          {otherError && <Alert severity="error">{setup.error.message}</Alert>}
          <TextField
            label="Admin username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
          <TextField
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
            error={short}
            helperText={`At least ${MIN_PASSWORD} characters. A short phrase is easier to remember.`}
          />
          <TextField
            label="Repeat password"
            type="password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            autoComplete="new-password"
            required
            error={mismatch}
            helperText={mismatch ? "The passwords don't match." : " "}
          />
          <Box sx={{ display: "flex", gap: 1.5 }}>
            <Button
              type="submit"
              variant="contained"
              size="large"
              startIcon={<PersonAddIcon />}
              disabled={setup.isPending || short || mismatch || password.length === 0}
            >
              Create admin
            </Button>
            <Button onClick={() => setStep(0)}>Back</Button>
          </Box>
        </Box>
      )}
    </AuthCard>
  );
}
