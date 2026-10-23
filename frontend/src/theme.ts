import { createTheme } from "@mui/material/styles";
import type {} from "@mui/material/themeCssVarsAugmentation";

// Ubuntu colour palette (https://design.ubuntu.com/brand/colour-palette) and its published
// tints only. Token tables and contrast ratios: docs/architecture.md.
export const ubuntu = {
  orange: "#E95420",
  orange60: "#F29879",
  orange50: "#F4AA90",
  orange30: "#F8CCBC",
  orange20: "#FBDDD2",
  orange10: "#FDEEE9",
  lightAubergine: "#77216F",
  lightAubergine40: "#C8A6C5",
  lightAubergine10: "#F1E8F0",
  midAubergine: "#5E2750",
  darkAubergine: "#2C001E",
  darkAubergine70: "#6B4C61",
  darkAubergine25: "#CABFC6",
  warmGrey: "#AEA79F",
  warmGrey25: "#EAE9E7",
  warmGrey15: "#F2F1F0",
  coolGrey: "#333333",
  textGrey: "#111111",
  white: "#FFFFFF",
} as const;

interface AttributionColours {
  confidentBg: string;
  confidentText: string;
  maybeBg: string;
  maybeText: string;
  maybeBorder: string;
}

declare module "@mui/material/styles" {
  interface Palette {
    attribution: AttributionColours;
    appBar: { background: string; inactive: string };
    highlight: { background: string; text: string };
  }
  interface PaletteOptions {
    attribution?: AttributionColours;
    appBar?: { background: string; inactive: string };
    highlight?: { background: string; text: string };
  }
}

const headings = {
  fontFamily: '"Barlow Semi Condensed", "Roboto", "Helvetica", "Arial", sans-serif',
  fontWeight: 600,
};

export const theme = createTheme({
  cssVariables: { colorSchemeSelector: "data" },
  colorSchemes: {
    light: {
      palette: {
        primary: { main: ubuntu.lightAubergine, dark: ubuntu.midAubergine, contrastText: ubuntu.white },
        secondary: { main: ubuntu.orange, light: ubuntu.orange60, contrastText: ubuntu.textGrey },
        // MUI's white label on its warning orange is only 3.1:1.
        warning: { main: "#ED6C02", contrastText: ubuntu.textGrey },
        background: { default: ubuntu.warmGrey15, paper: ubuntu.white },
        text: { primary: ubuntu.textGrey, secondary: ubuntu.darkAubergine70 },
        divider: ubuntu.warmGrey25,
        appBar: { background: ubuntu.darkAubergine, inactive: ubuntu.darkAubergine25 },
        highlight: { background: ubuntu.orange30, text: ubuntu.textGrey },
        attribution: {
          confidentBg: ubuntu.lightAubergine10,
          confidentText: ubuntu.midAubergine,
          maybeBg: ubuntu.orange10,
          maybeText: ubuntu.textGrey,
          maybeBorder: ubuntu.orange,
        },
      },
    },
    dark: {
      palette: {
        primary: { main: ubuntu.lightAubergine40, contrastText: ubuntu.textGrey },
        secondary: { main: ubuntu.orange, light: ubuntu.orange60, contrastText: ubuntu.textGrey },
        // MUI's white label on its dark-scheme error red is only 3.7:1.
        error: { main: "#F44336", contrastText: ubuntu.textGrey },
        background: { default: ubuntu.textGrey, paper: ubuntu.coolGrey },
        text: { primary: ubuntu.white, secondary: ubuntu.warmGrey },
        divider: "rgba(174,167,159,0.24)",
        appBar: { background: ubuntu.darkAubergine, inactive: ubuntu.darkAubergine25 },
        // MUI paints the AppBar with these in dark mode, overriding styleOverrides.
        AppBar: { darkBg: ubuntu.darkAubergine, darkColor: ubuntu.white },
        highlight: { background: ubuntu.orange50, text: ubuntu.textGrey },
        attribution: {
          confidentBg: ubuntu.midAubergine,
          confidentText: ubuntu.white,
          maybeBg: "transparent",
          maybeText: ubuntu.orange20,
          maybeBorder: ubuntu.orange60,
        },
      },
    },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h1: { ...headings, fontSize: "1.875rem" },
    h2: { ...headings, fontSize: "1.375rem" },
    h3: { ...headings, fontSize: "1.25rem" },
    h4: headings,
    h5: headings,
    h6: headings,
    button: { textTransform: "none", fontWeight: 500 },
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: ({ theme }) => ({ backgroundColor: theme.vars.palette.appBar.background }),
      },
    },
  },
});

export const monoFontFamily = '"Roboto Mono", ui-monospace, monospace';
