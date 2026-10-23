import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AuthStateName } from "../../api/hooks";
import { auth, type FakeApi, installFakeApi, queueList, settings, status } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

let state: AuthStateName;

function serve(initial: AuthStateName): FakeApi {
  state = initial;
  const api = installFakeApi();
  api.on("GET /status", status());
  api.on("GET /auth/state", () => ({ body: auth(state) }));
  api.on("GET /admin/settings", settings());
  api.on("GET /admin/queues", queueList());
  return api;
}

describe("admin routing", () => {
  it.each([
    ["setup_required" as const, "/admin/settings", "/admin/setup"],
    ["setup_required" as const, "/admin/login", "/admin/setup"],
    ["login_required" as const, "/admin", "/admin/login"],
    ["login_required" as const, "/admin/settings", "/admin/login"],
    ["logged_in" as const, "/admin", "/admin/settings"],
    ["logged_in" as const, "/admin/login", "/admin/settings"],
  ])("with %s sends %s to %s", async (initial, from, to) => {
    serve(initial);
    const app = renderApp(from);
    await vi.waitFor(() => expect(app.location()).toBe(to));
  });
});

describe("signing in", () => {
  it("opens the settings after a correct login", async () => {
    const api = serve("login_required");
    api.on("POST /auth/login", () => {
      state = "logged_in";
      return { body: auth("logged_in") };
    });
    const app = renderApp("/admin/login");
    await userEvent.type(await screen.findByLabelText(/Username/), "admin");
    await userEvent.type(screen.getByLabelText(/Password/), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(app.location()).toBe("/admin/settings");
    const login = api.sent.find((r) => r.path === "/auth/login");
    expect(login?.body).toEqual({ username: "admin", password: "correct horse battery" });
    expect(login?.headers["X-Transcribr"]).toBe("1");
  });

  it("shows the server's message for a wrong password", async () => {
    const api = serve("login_required");
    api.on("POST /auth/login", () => ({
      status: 401,
      body: { error: { code: "wrong_login", message: "Wrong username or password." } },
    }));
    const app = renderApp("/admin/login");
    await userEvent.type(await screen.findByLabelText(/Username/), "admin");
    await userEvent.type(screen.getByLabelText(/Password/), "wrong password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Wrong username or password.")).toBeInTheDocument();
    expect(app.location()).toBe("/admin/login");
  });

  it("tells how to reset a forgotten password", async () => {
    serve("login_required");
    renderApp("/admin/login");
    expect(await screen.findByText(/transcribr reset-admin/)).toBeInTheDocument();
  });
});

describe("first-time setup", () => {
  async function enterCode(code: string) {
    await userEvent.type(await screen.findByLabelText(/Setup code/), code);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  }

  async function enterAccount(password: string, repeat = password) {
    await userEvent.type(screen.getByLabelText(/^Password/), password);
    await userEvent.type(screen.getByLabelText(/Repeat password/), repeat);
  }

  it("creates the admin with the setup code and opens the settings", async () => {
    const api = serve("setup_required");
    api.on("POST /auth/setup", () => {
      state = "logged_in";
      return { body: auth("logged_in") };
    });
    const app = renderApp("/admin");
    await enterCode("ABCD-EFGH-JK");
    await enterAccount("a long enough passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Create admin" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(app.location()).toBe("/admin/settings");
    expect(api.sent.find((r) => r.path === "/auth/setup")?.body).toEqual({
      code: "ABCD-EFGH-JK",
      username: "admin",
      password: "a long enough passphrase",
    });
  });

  it("returns to the code step after a wrong setup code", async () => {
    const api = serve("setup_required");
    api.on("POST /auth/setup", () => ({
      status: 403,
      body: { error: { code: "wrong_setup_code", message: "That setup code is wrong." } },
    }));
    renderApp("/admin/setup");
    await enterCode("WRONG-CODE");
    await enterAccount("a long enough passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Create admin" }));
    expect(await screen.findByText("That setup code is wrong.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Setup code/)).toHaveValue("WRONG-CODE");
  });

  it("won't create an admin with a short password or a mismatched repeat", async () => {
    const api = serve("setup_required");
    renderApp("/admin/setup");
    await enterCode("ABCD-EFGH-JK");
    await enterAccount("too short");
    expect(screen.getByRole("button", { name: "Create admin" })).toBeDisabled();
    expect(screen.getByLabelText(/^Password/)).toHaveAttribute("aria-invalid", "true");

    await userEvent.clear(screen.getByLabelText(/^Password/));
    await userEvent.clear(screen.getByLabelText(/Repeat password/));
    await enterAccount("a long enough passphrase", "a different passphrase");
    expect(screen.getByText("The passwords don't match.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create admin" })).toBeDisabled();
    expect(api.sent.some((r) => r.path === "/auth/setup")).toBe(false);
  });
});
