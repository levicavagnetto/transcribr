import { Navigate, Route, Routes } from "react-router";

import { AdminGate } from "./pages/admin/AdminGate";
import { Login } from "./pages/admin/Login";
import { Settings } from "./pages/admin/Settings";
import { Setup } from "./pages/admin/Setup";
import { Home } from "./pages/Home";
import { AppShell } from "./shell/AppShell";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route
          path="/admin/*"
          element={
            <AdminGate>
              <Routes>
                <Route path="setup" element={<Setup />} />
                <Route path="login" element={<Login />} />
                <Route path="settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/admin/settings" replace />} />
              </Routes>
            </AdminGate>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
