import Chip from "@mui/material/Chip";
import type { Theme } from "@mui/material/styles";

import type { CallState } from "../api/hooks";

export const STATE_LABEL: Record<CallState, string> = {
  transcribed: "Transcribed",
  waiting: "Waiting",
  processing: "Processing",
  not_transcribed: "Not transcribed",
  failed: "Failed",
};

// Colours from the theme, so both schemes keep the contrast the theme test checks.
function colours(theme: Theme, state: CallState) {
  const p = theme.vars.palette;
  switch (state) {
    case "transcribed":
      return { bgcolor: p.attribution.confidentBg, color: p.attribution.confidentText };
    case "processing":
      return { bgcolor: "transparent", color: p.text.primary, border: `1px solid ${p.secondary.main}` };
    case "not_transcribed":
      return { bgcolor: "transparent", color: p.text.secondary, border: `1px solid ${p.text.secondary}` };
    case "failed":
      return { bgcolor: p.error.main, color: p.error.contrastText };
    default:
      return {};
  }
}

export function StateChip({ state }: { state: CallState }) {
  return <Chip size="small" label={STATE_LABEL[state]} sx={(theme) => ({ fontWeight: 500, ...colours(theme, state) })} />;
}
