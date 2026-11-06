import InitColorSchemeScript from "@mui/material/InitColorSchemeScript";
import react from "@vitejs/plugin-react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

import { COLOR_SCHEME_ATTRIBUTE, COLOR_SCHEME_STORAGE_KEY, MODE_STORAGE_KEY } from "./src/colorScheme.ts";

// MUI's InitColorSchemeScript, rendered into <head> so the saved or system scheme is applied
// before React loads and the page never flashes the light theme.
export const colorSchemeScript = renderToStaticMarkup(
  createElement(InitColorSchemeScript, {
    attribute: COLOR_SCHEME_ATTRIBUTE,
    defaultMode: "system",
    modeStorageKey: MODE_STORAGE_KEY,
    colorSchemeStorageKey: COLOR_SCHEME_STORAGE_KEY,
  }),
);

function initColorScheme(): Plugin {
  return {
    name: "transcribr-init-color-scheme",
    transformIndexHtml: (html) => html.replace("<!-- init-color-scheme -->", colorSchemeScript),
  };
}

// In development the API runs separately (uvicorn on :8000); in production FastAPI serves dist/.
export default defineConfig({
  plugins: [react(), initColorScheme()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
