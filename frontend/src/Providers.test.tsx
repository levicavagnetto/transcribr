import { render } from "@testing-library/react";

import { Providers } from "./Providers";

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
});
