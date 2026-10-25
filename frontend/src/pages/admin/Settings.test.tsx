import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Status } from "../../api/hooks";
import { auth, DEFAULT_PROMPT, type FakeApi, installFakeApi, queueList, settings, status } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

function serve(statusOverrides: Partial<Status> = {}): FakeApi {
  const api = installFakeApi();
  api.on("GET /status", status(statusOverrides));
  api.on("GET /auth/state", auth("logged_in"));
  api.on("GET /admin/settings", settings({ store_queues: ["tireProz-salescustserv"] }));
  api.on("GET /admin/queues", queueList());
  return api;
}

describe("the settings page", () => {
  it("shows the queues read from Ravon with the chosen ones ticked", async () => {
    serve();
    renderApp("/admin/settings");
    const queues = within(await screen.findByRole("region", { name: "Store queues" }));
    expect(await queues.findByRole("checkbox", { name: "Stillwater Sales/CS (x600)" })).toBeChecked();
    expect(queues.getByRole("checkbox", { name: "SWafterHRS (x599)" })).not.toBeChecked();
    expect(queues.getByRole("checkbox", { name: "Hudson Sales/CS (x700)" })).not.toBeChecked();
  });

  it("saves the changed values", async () => {
    const api = serve();
    api.on("PUT /admin/settings", (body: unknown) => ({ body: settings(body as object) }));
    renderApp("/admin/settings");
    await userEvent.click(await screen.findByRole("checkbox", { name: "SWafterHRS (x599)" }));
    const interval = screen.getByLabelText("Check every (minutes)");
    await userEvent.clear(interval);
    await userEvent.type(interval, "5");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Settings saved.")).toBeInTheDocument();
    const put = api.sent.find((r) => r.method === "PUT");
    expect(put?.body).toEqual({
      store_queues: ["tireProz-salescustserv", "tireProz-SWafterHRS"],
      poll_interval_minutes: 5,
      time_zone: "America/Chicago",
    });
    expect(put?.headers["X-Transcribr"]).toBe("1");
  });

  it("drops leading zeros and letters from the minutes", async () => {
    serve();
    renderApp("/admin/settings");
    const interval = await screen.findByLabelText("Check every (minutes)");
    await userEvent.clear(interval);
    await userEvent.type(interval, "02");
    expect(interval).toHaveValue("2");
    await userEvent.type(interval, "x0");
    expect(interval).toHaveValue("20");
  });

  it("checks the minutes against the limits on leaving the field", async () => {
    serve();
    renderApp("/admin/settings");
    const interval = await screen.findByLabelText("Check every (minutes)");
    await userEvent.clear(interval);
    await userEvent.type(interval, "45");
    expect(screen.queryByText(/between 1 and 30/)).not.toBeInTheDocument();
    await userEvent.tab();
    expect(screen.getByText(/between 1 and 30/)).toBeInTheDocument();
    expect(interval).toHaveAttribute("aria-invalid", "true");

    await userEvent.clear(interval);
    expect(screen.getByText(/between 1 and 30/)).toBeInTheDocument();
    await userEvent.type(interval, "15");
    expect(screen.queryByText(/between 1 and 30/)).not.toBeInTheDocument();
    expect(interval).toHaveAttribute("aria-invalid", "false");
  });

  it("shows a value the server rejected next to its field", async () => {
    const api = serve();
    api.on("PUT /admin/settings", () => ({
      status: 422,
      body: { error: { code: "invalid_setting", message: "Unknown time zone.", key: "time_zone" } },
    }));
    renderApp("/admin/settings");
    const zone = await screen.findByLabelText("Store time zone");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Unknown time zone.")).toBeInTheDocument();
    expect(zone).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Check every (minutes)")).toHaveAttribute("aria-invalid", "false");
    expect(screen.queryByText("Settings saved.")).not.toBeInTheDocument();
  });

  it("asks the worker to re-read the queue list", async () => {
    const api = serve();
    api.on("POST /admin/queues/refresh", { requested: true });
    renderApp("/admin/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Refresh list" }));
    await vi.waitFor(() => expect(api.sent.some((r) => r.path === "/admin/queues/refresh")).toBe(true));
  });

  it("says when the worker hasn't read the queue list yet", async () => {
    const api = serve();
    api.on("GET /admin/queues", queueList({ queues: [], fetched_at: null }));
    renderApp("/admin/settings");
    expect(await screen.findByText(/hasn't read Ravon's queue list yet/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /tireProz-salescustserv \(not in Ravon's list\)/ })).toBeChecked();
  });

  it("shows the Ravon login state and retries the login", async () => {
    const api = serve({ ravon_state: "login_failed", ravon_error: "Ravon refused the login." });
    api.on("POST /admin/ravon/retry-login", { requested: true });
    renderApp("/admin/settings");
    const ravon = within(await screen.findByRole("region", { name: "Ravon login" }));
    expect(await ravon.findByText("Login failed")).toBeInTheDocument();
    expect(ravon.getByText("Ravon refused the login.")).toBeInTheDocument();
    await userEvent.click(ravon.getByRole("button", { name: "Retry login" }));
    expect(await ravon.findByText(/will try again/)).toBeInTheDocument();
  });

  it("changes the admin password", async () => {
    const api = serve();
    api.on("POST /admin/password", { changed: true });
    renderApp("/admin/settings");
    const account = within(await screen.findByRole("region", { name: "Admin account" }));
    await userEvent.type(account.getByLabelText(/Current password/), "old passphrase here");
    await userEvent.type(account.getByLabelText(/New password/), "a brand new passphrase");
    await userEvent.click(account.getByRole("button", { name: "Change password" }));
    expect(await account.findByText("Password changed.")).toBeInTheDocument();
    expect(api.sent.find((r) => r.path === "/admin/password")?.body).toEqual({
      current: "old passphrase here",
      new: "a brand new passphrase",
    });
    expect(account.getByLabelText(/Current password/)).toHaveValue("");
  });

  it("shows why a password change was refused", async () => {
    const api = serve();
    api.on("POST /admin/password", () => ({
      status: 422,
      body: { error: { code: "password_too_short", message: "Use at least 12 characters." } },
    }));
    renderApp("/admin/settings");
    const account = within(await screen.findByRole("region", { name: "Admin account" }));
    await userEvent.type(account.getByLabelText(/Current password/), "old passphrase here");
    await userEvent.type(account.getByLabelText(/New password/), "short");
    await userEvent.click(account.getByRole("button", { name: "Change password" }));
    expect(await account.findByText("Use at least 12 characters.")).toBeInTheDocument();
  });
});

describe("the research prompt", () => {
  it("saves an edited prompt on its own", async () => {
    const api = serve();
    api.on("PUT /admin/settings", (body: unknown) => ({ body: settings(body as object) }));
    renderApp("/admin/settings");
    const section = within(await screen.findByRole("region", { name: "Research prompt" }));
    const box = section.getByLabelText("Prompt");
    expect(box).toHaveValue(DEFAULT_PROMPT);
    expect(section.getByText(`${DEFAULT_PROMPT.length} / 4,000`)).toBeInTheDocument();
    await userEvent.clear(box);
    await userEvent.type(box, "Find three tire options.");
    expect(section.getByText("24 / 4,000")).toBeInTheDocument();
    await userEvent.click(section.getByRole("button", { name: "Save prompt" }));
    expect(await screen.findByText("Research prompt saved.")).toBeInTheDocument();
    const put = api.sent.find((r) => r.method === "PUT");
    expect(put?.body).toEqual({ research_prompt: "Find three tire options." });
  });

  it("won't save an empty prompt and says the old one is still used", async () => {
    const api = serve();
    renderApp("/admin/settings");
    const section = within(await screen.findByRole("region", { name: "Research prompt" }));
    await userEvent.clear(section.getByLabelText("Prompt"));
    await userEvent.click(section.getByRole("button", { name: "Save prompt" }));
    expect(section.getByText("The prompt can't be empty. The previous prompt is still in use.")).toBeInTheDocument();
    expect(section.getByLabelText("Prompt")).toHaveAttribute("aria-invalid", "true");
    expect(api.sent.some((r) => r.method === "PUT")).toBe(false);
  });

  it("puts the default back", async () => {
    serve();
    renderApp("/admin/settings");
    const section = within(await screen.findByRole("region", { name: "Research prompt" }));
    await userEvent.clear(section.getByLabelText("Prompt"));
    await userEvent.type(section.getByLabelText("Prompt"), "something else");
    await userEvent.click(section.getByRole("button", { name: "Reset to the default" }));
    expect(section.getByLabelText("Prompt")).toHaveValue(DEFAULT_PROMPT);
  });

  it("shows a prompt the server refused", async () => {
    const api = serve();
    api.on("PUT /admin/settings", () => ({
      status: 422,
      body: {
        error: {
          code: "invalid_setting",
          message: "The research prompt must be 1 to 4,000 characters, and not only spaces.",
          key: "research_prompt",
        },
      },
    }));
    renderApp("/admin/settings");
    const section = within(await screen.findByRole("region", { name: "Research prompt" }));
    await userEvent.type(section.getByLabelText("Prompt"), " more");
    await userEvent.click(section.getByRole("button", { name: "Save prompt" }));
    expect(await section.findByText(/must be 1 to 4,000 characters/)).toBeInTheDocument();
  });
});
