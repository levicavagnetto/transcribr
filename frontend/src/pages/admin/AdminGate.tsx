import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useAuthState } from "../../api/hooks";

const PUBLIC = { setup_required: "/admin/setup", login_required: "/admin/login" } as const;

// Sends every /admin page to setup or login when there's no admin session, and away from them
// once logged in. The server checks the session on every admin request; this is only routing.
export function AdminGate({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { data, isLoading } = useAuthState();
  if (isLoading || !data) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 6 }}>
        <CircularProgress aria-label="Loading" />
      </Box>
    );
  }
  if (data.state !== "logged_in") {
    const target = PUBLIC[data.state];
    return pathname === target ? children : <Navigate to={target} replace />;
  }
  if (pathname === PUBLIC.setup_required || pathname === PUBLIC.login_required || pathname === "/admin") {
    return <Navigate to="/admin/settings" replace />;
  }
  return children;
}
