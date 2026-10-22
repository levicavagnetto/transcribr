import { ThemeProvider } from "@mui/material/styles";
import { render, screen } from "@testing-library/react";

import { App } from "./App";
import { theme, ubuntu } from "./theme";

describe("App", () => {
  it("renders the app bar with the product name", () => {
    render(
      <ThemeProvider theme={theme}>
        <App />
      </ThemeProvider>,
    );
    expect(screen.getByText("Transcribr")).toBeInTheDocument();
  });
});

describe("theme", () => {
  it("defines light and dark schemes from the Ubuntu palette", () => {
    const light = theme.colorSchemes.light?.palette;
    const dark = theme.colorSchemes.dark?.palette;
    expect(light?.primary.main).toBe(ubuntu.lightAubergine);
    expect(dark?.primary.main).toBe(ubuntu.lightAubergine40);
    expect(light?.appBar.background).toBe(ubuntu.darkAubergine);
    expect(dark?.background.paper).toBe(ubuntu.coolGrey);
  });
});
