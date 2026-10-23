import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

import { COLOR_SCHEME_STORAGE_KEY, MODE_STORAGE_KEY } from "./colorScheme";
import { theme } from "./theme";

// Tests pass their own client (no retries) so error states show at once.
export function Providers({ children, client }: { children: ReactNode; client?: QueryClient }) {
  const [queryClient] = useState(() => client ?? new QueryClient());
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
