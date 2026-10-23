import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MODE_STORAGE_KEY } from "./colorScheme";
import { Providers } from "./Providers";
import { ThemeMenu } from "./shell/ThemeMenu";

function mockSystemDark(dark: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === "(prefers-color-scheme: dark)" ? dark : false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe("colour scheme", () => {
  afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-dark");
    document.documentElement.removeAttribute("data-light");
  });

  it("follows a dark system setting", () => {
    mockSystemDark(true);
    render(<Providers>page</Providers>);
    expect(document.documentElement).toHaveAttribute("data-dark");
  });

  it("ignores another app's saved MUI mode on the same origin", () => {
    localStorage.setItem("mui-mode", "light");
    mockSystemDark(true);
    render(<Providers>page</Providers>);
    expect(document.documentElement).toHaveAttribute("data-dark");
  });

  it("keeps the menu choice across a remount", async () => {
    mockSystemDark(false);
    const first = render(
      <Providers>
        <ThemeMenu />
      </Providers>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Theme: System" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Dark" }));
    expect(document.documentElement).toHaveAttribute("data-dark");
    expect(localStorage.getItem(MODE_STORAGE_KEY)).toBe("dark");
    first.unmount();
    document.documentElement.removeAttribute("data-dark");

    render(
      <Providers>
        <ThemeMenu />
      </Providers>,
    );
    expect(screen.getByRole("button", { name: "Theme: Dark" })).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("data-dark");
  });
});
