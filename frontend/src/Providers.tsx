import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

import { theme } from "./theme";

// Our own keys: MUI's default `mui-mode` is shared by every app on the same origin
// (every Vite project on localhost:5173), and a stale value there overrides the system setting.
export const MODE_STORAGE_KEY = "transcribr-mode";
export const COLOR_SCHEME_STORAGE_KEY = "transcribr-color-scheme";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return (
    <ThemeProvider
      theme={theme}
      defaultMode="system"
      modeStorageKey={MODE_STORAGE_KEY}
      colorSchemeStorageKey={COLOR_SCHEME_STORAGE_KEY}
    >
      <CssBaseline />
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
}
