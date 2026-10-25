import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import LogoutIcon from "@mui/icons-material/Logout";
import AppBar from "@mui/material/AppBar";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import { Link as RouterLink, useLocation, useNavigate } from "react-router";

import { useAuthState, useLogout, useStatus } from "../api/hooks";
import { clockTime } from "../format";
import { StatusBanner } from "./StatusBanner";
import { ThemeMenu } from "./ThemeMenu";

const ADMIN_TABS = [{ path: "/admin/settings", label: "Settings" }];

function WorkerChip() {
  const { data } = useStatus();
  if (!data) return null;
  const label = data.worker_running
    ? `${data.waiting} waiting · ${data.failed_last_24h} failed in 24 h · checked ${clockTime(data.last_poll_ok)}`
    : "Worker stopped";
  return (
    <Chip
      size="small"
      label={label}
      sx={{
        bgcolor: "rgba(255,255,255,0.12)",
        color: "common.white",
        display: { xs: "none", md: "inline-flex" },
        "& .MuiChip-label::before": {
          content: '""',
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: "50%",
          mr: 1,
          bgcolor: data.worker_running ? "success.light" : "error.light",
        },
      }}
    />
  );
}

function AdminBar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const auth = useAuthState();
  const logout = useLogout();
  const loggedIn = auth.data?.state === "logged_in";
  return (
    <>
      <Chip
        icon={<AdminPanelSettingsIcon />}
        label="Admin"
        size="small"
        color="secondary"
        sx={{ fontWeight: 500 }}
      />
      {loggedIn && (
        <Tabs
          value={ADMIN_TABS.some((t) => t.path === pathname) ? pathname : false}
          textColor="inherit"
          sx={{ flexGrow: 1, "& .MuiTabs-indicator": { bgcolor: "secondary.main", height: 3 } }}
        >
          {ADMIN_TABS.map((tab) => (
            <Tab key={tab.path} value={tab.path} label={tab.label} component={RouterLink} to={tab.path} />
          ))}
        </Tabs>
      )}
      {!loggedIn && <Box sx={{ flexGrow: 1 }} />}
      <Button color="inherit" component={RouterLink} to="/" startIcon={<ArrowBackIcon />}>
        Back to app
      </Button>
      {loggedIn && (
        <>
          <Avatar sx={{ width: 32, height: 32, bgcolor: "primary.dark", fontSize: 14 }}>
            {(auth.data?.username ?? "A").slice(0, 1).toUpperCase()}
          </Avatar>
          <Typography variant="body2">{auth.data?.username}</Typography>
          <Button
            color="inherit"
            variant="outlined"
            startIcon={<LogoutIcon />}
            onClick={() => logout.mutate(undefined, { onSuccess: () => void navigate("/admin/login") })}
          >
            Log out
          </Button>
        </>
      )}
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const inAdmin = pathname.startsWith("/admin");
  const status = useStatus();
  const auth = useAuthState();
  return (
    <Box sx={{ minHeight: "100vh", display: "flex", flexDirection: "column", bgcolor: "background.default" }}>
      <AppBar position="static">
        <Toolbar sx={{ gap: 2, flexWrap: "wrap", maxWidth: 1400, width: "100%", mx: "auto" }}>
          <GraphicEqIcon sx={{ color: "secondary.main" }} />
          <Typography variant="h1" component="div" sx={{ fontSize: 24, fontWeight: 700 }}>
            Transcribr
          </Typography>
          {inAdmin ? <AdminBar /> : <Box sx={{ flexGrow: 1 }} />}
          {!inAdmin && <WorkerChip />}
          <ThemeMenu />
        </Toolbar>
      </AppBar>
      <StatusBanner status={status.data} isAdmin={auth.data?.state === "logged_in"} />
      <Box component="main" sx={{ flexGrow: 1, width: "100%", maxWidth: 1400, mx: "auto", p: 3 }}>
        {children}
      </Box>
      <Box
        component="footer"
        sx={{
          maxWidth: 1400,
          width: "100%",
          mx: "auto",
          px: 3,
          pb: 3,
          display: "flex",
          justifyContent: "space-between",
          color: "text.secondary",
          fontSize: 12,
        }}
      >
        <span>Transcribr</span>
        {!inAdmin && (
          <Link component={RouterLink} to="/admin" color="inherit" sx={{ display: "inline-flex", gap: 0.5 }}>
            <AdminPanelSettingsIcon sx={{ fontSize: 16 }} />
            Admin
          </Link>
        )}
      </Box>
    </Box>
  );
}
