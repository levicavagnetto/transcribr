import Chip from "@mui/material/Chip";

import type { Attribution } from "../api/hooks";

// A person on a call. Maybe chips are dashed, with the theme's attribution colours in both schemes.
export function PersonChip({ attribution, size = "small" }: { attribution: Attribution; size?: "small" | "medium" }) {
  const maybe = attribution.status === "maybe";
  return (
    <Chip
      size={size}
      label={maybe ? `${attribution.display_name}?` : attribution.display_name}
      aria-label={maybe ? `Maybe ${attribution.display_name}` : attribution.display_name}
      sx={(theme) => {
        const a = theme.vars.palette.attribution;
        return maybe
          ? { bgcolor: a.maybeBg, color: a.maybeText, border: `1px dashed ${a.maybeBorder}` }
          : { bgcolor: a.confidentBg, color: a.confidentText };
      }}
    />
  );
}
