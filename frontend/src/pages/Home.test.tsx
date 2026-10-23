import { screen } from "@testing-library/react";

import type { Status } from "../api/hooks";
import { auth, installFakeApi, status } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

function serve(overrides: Partial<Status>) {
  const api = installFakeApi();
  api.on("GET /status", status(overrides));
  api.on("GET /auth/state", auth("login_required"));
}

function figure(label: string): string | null | undefined {
  return screen.getByText(label).nextElementSibling?.textContent;
}

describe("the home page", () => {
  it("shows the collection status when working", async () => {
    serve({ listed_today: 15, transcribed_today: 12, waiting: 2, failed_last_24h: 1 });
    renderApp("/");
    await screen.findByText("Listed today");
    expect(figure("Listed today")).toBe("15");
    expect(figure("Transcribed today")).toBe("12");
    expect(figure("Waiting")).toBe("2");
    expect(figure("Failed")).toBe("1");
    expect(screen.getByText("Last check")).toBeInTheDocument();
    expect(screen.queryByText(/First-time setup/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No store queues are chosen/)).not.toBeInTheDocument();
  });

  it("points to first-time setup when there is no admin", async () => {
    serve({ admin_exists: false, queues_chosen: false });
    renderApp("/");
    expect(await screen.findByText(/First-time setup/)).toBeInTheDocument();
  });

  it("says no calls are collected until a queue is chosen", async () => {
    serve({ queues_chosen: false, listed_today: 0, last_poll_ok: null });
    renderApp("/");
    expect(await screen.findByText(/No store queues are chosen yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "/admin/settings" })).toHaveAttribute("href", "/admin/settings");
    expect(figure("Last check")).toBe("never");
  });

  it("says when the server can't be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    renderApp("/");
    expect(await screen.findByText(/Can't reach the Transcribr server/)).toBeInTheDocument();
  });
});
