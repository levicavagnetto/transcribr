import { Navigate, Route, Routes } from "react-router";

import { AdminGate } from "./pages/admin/AdminGate";
import { Login } from "./pages/admin/Login";
import { Settings } from "./pages/admin/Settings";
import { Setup } from "./pages/admin/Setup";
import { Call } from "./pages/Call";
import { Calls } from "./pages/Calls";
import { AppShell } from "./shell/AppShell";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Calls />} />
        <Route path="/calls/:id" element={<Call />} />
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
