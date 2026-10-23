import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { auth, installFakeApi, status } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";
import { problemsFrom } from "./StatusBanner";

describe("problemsFrom", () => {
  it("reports nothing when everything works", () => {
    expect(problemsFrom(status())).toEqual([]);
  });

  it.each([
    [{ ravon_state: "no_credentials" as const }, "no_credentials", /login details are missing/],
    [{ ravon_state: "login_failed" as const }, "login_failed", /login failed/],
    [{ ravon_state: "page_format_changed" as const }, "page_format_changed", /page has changed/],
    [{ ravon_state: "unreachable" as const }, "unreachable", /isn't answering/],
    [{ worker_running: false }, "worker_stopped", /worker has stopped/],
    [{ worker_running: false, worker_last_seen: null }, "worker_stopped", /hasn't started yet/],
    [{ guard_violations: 2 }, "guard_violations", /2 request\(s\) to Ravon were blocked/],
  ])("reports %o", (overrides, id, title) => {
    const problems = problemsFrom(status(overrides));
    expect(problems.map((p) => p.id)).toEqual([id]);
    expect(problems[0]!.title).toMatch(title);
  });
});

describe("the status banner", () => {
  it("shows each problem on the home page", async () => {
    const api = installFakeApi();
    api.on("GET /status", status({ ravon_state: "unreachable", guard_violations: 1 }));
    api.on("GET /auth/state", auth("login_required"));
    renderApp("/");
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.map((a) => a.textContent)).toEqual([
      expect.stringMatching(/Ravon isn't answering/),
      expect.stringMatching(/1 request\(s\) to Ravon were blocked/),
    ]);
  });

  it("offers Retry login only to a logged-in admin", async () => {
    const api = installFakeApi();
    api.on("GET /status", status({ ravon_state: "login_failed" }));
    api.on("GET /auth/state", auth("login_required"));
    const first = renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(within(alert).queryByRole("button", { name: "Retry login" })).not.toBeInTheDocument();
    first.unmount();

    api.on("GET /auth/state", auth("logged_in"));
    api.on("POST /admin/ravon/retry-login", { requested: true });
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Retry login" }));
    await vi.waitFor(() => expect(api.sent.some((r) => r.path === "/admin/ravon/retry-login")).toBe(true));
  });
});
