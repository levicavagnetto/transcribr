// Our own keys: MUI's default `mui-mode` is shared by every app on the same origin
// (every Vite project on localhost:5173), and a stale value there overrides the system setting.
// Shared by the ThemeProvider and the pre-React script that vite.config.ts puts in index.html.
export const MODE_STORAGE_KEY = "transcribr-mode";
export const COLOR_SCHEME_STORAGE_KEY = "transcribr-color-scheme";
export const COLOR_SCHEME_ATTRIBUTE = "data";
