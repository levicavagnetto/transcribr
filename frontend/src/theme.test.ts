import { getContrastRatio } from "@mui/material/styles";

import { theme, ubuntu } from "./theme";

describe.each(["light", "dark"] as const)("the %s scheme", (scheme) => {
  const p = theme.colorSchemes[scheme]!.palette;
  const maybeBg = p.attribution.maybeBg === "transparent" ? p.background.paper : p.attribution.maybeBg;
  const pairs: [string, string, string][] = [
    ["body text on the page", p.text.primary, p.background.default],
    ["body text on cards", p.text.primary, p.background.paper],
    ["secondary text on the page", p.text.secondary, p.background.default],
    ["secondary text on cards", p.text.secondary, p.background.paper],
    ["links and text buttons on the page", p.primary.main, p.background.default],
    ["links and text buttons on cards", p.primary.main, p.background.paper],
    ["filled primary buttons", p.primary.contrastText, p.primary.main],
    ["filled orange accents", p.secondary.contrastText, p.secondary.main],
    ["app bar text", ubuntu.white, p.appBar.background],
    ["inactive app bar tabs", p.appBar.inactive, p.appBar.background],
    ["search highlights", p.highlight.text, p.highlight.background],
    ["confident speaker labels", p.attribution.confidentText, p.attribution.confidentBg],
    ["unconfirmed speaker labels", p.attribution.maybeText, maybeBg],
    ["success chips", p.success.contrastText, p.success.main],
    ["warning chips", p.warning.contrastText, p.warning.main],
    ["error chips", p.error.contrastText, p.error.main],
  ];

  it.each(pairs)("gives %s at least 4.5:1", (_name, text, background) => {
    expect(getContrastRatio(text, background)).toBeGreaterThanOrEqual(4.5);
  });
});
