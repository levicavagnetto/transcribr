import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AuthStateName } from "../api/hooks";
import { auth, installFakeApi, queueList, settings, status } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

function serve(state: AuthStateName) {
  const api = installFakeApi();
  api.on("GET /status", status());
  api.on("GET /auth/state", auth(state));
  api.on("GET /admin/settings", settings());
  api.on("GET /admin/queues", queueList());
  return api;
}

describe("the app shell", () => {
  it("shows a small Admin link in the footer and the worker state", async () => {
    serve("login_required");
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Admin" })).toHaveAttribute("href", "/admin");
    expect(await screen.findByText("2 waiting · 1 failed in 24 h")).toBeInTheDocument();
  });

  it("hides the admin links without a session", async () => {
    serve("login_required");
    renderApp("/admin/login");
    expect(await screen.findByRole("heading", { name: "Admin sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Settings" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Log out" })).not.toBeInTheDocument();
  });

  it("shows the admin links to a logged-in admin", async () => {
    serve("logged_in");
    renderApp("/admin/settings");
    expect(await screen.findByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to app" })).toHaveAttribute("href", "/");
  });

  it("logs out and returns to the sign-in page", async () => {
    const api = serve("logged_in");
    api.on("POST /auth/logout", auth("login_required"));
    const app = renderApp("/admin/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Log out" }));
    expect(await screen.findByRole("heading", { name: "Admin sign in" })).toBeInTheDocument();
    expect(app.location()).toBe("/admin/login");
    expect(screen.queryByRole("tab", { name: "Settings" })).not.toBeInTheDocument();
  });
});
