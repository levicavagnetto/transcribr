import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Profile } from "../../api/hooks";
import { auth, type FakeApi, installFakeApi, profile, status } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

function serve(profiles: Profile[] = [profile()]): FakeApi {
  const api = installFakeApi();
  api.on("GET /status", status());
  api.on("GET /auth/state", auth("logged_in"));
  api.on("GET /admin/profiles", { profiles });
  return api;
}

describe("the People screen", () => {
  it("is in the admin navigation next to Settings", async () => {
    serve();
    renderApp("/admin/people");
    expect(await screen.findByRole("tab", { name: "People" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument();
  });

  it("sends someone without an admin session to the login", async () => {
    const api = serve();
    api.on("GET /auth/state", auth("login_required"));
    const { location } = renderApp("/admin/people");
    await vi.waitFor(() => expect(location()).toBe("/admin/login"));
    expect(api.sent.some((r) => r.path.startsWith("/admin/profiles"))).toBe(false);
  });

  it("lists each person with their name spellings and how calls were found", async () => {
    serve();
    renderApp("/admin/people");
    const card = within(await screen.findByRole("region", { name: "Nolan" }));
    expect(card.getByText("Nolen")).toBeInTheDocument();
    expect(card.getByText(/11 by name · 3 by hand · 3 still Maybe/)).toBeInTheDocument();
    expect(screen.queryByText(/voice/i)).toBeNull();
  });

  it("adds a person with their spellings", async () => {
    const api = serve([]);
    api.on("POST /admin/profiles", (body: unknown) => ({ body: profile({ id: 7, ...(body as object) }) }));
    renderApp("/admin/people");
    const form = within(await screen.findByRole("region", { name: "Add a person" }));
    await userEvent.type(form.getByLabelText(/^Name/), "Dana Reyes");
    await userEvent.type(form.getByLabelText(/Spellings/), "Dana, Danna");
    await userEvent.click(form.getByRole("button", { name: "Add" }));
    const post = api.sent.find((r) => r.method === "POST");
    expect(post?.body).toEqual({ display_name: "Dana Reyes", variants: ["Dana", "Danna"] });
  });

  it("edits a person's spellings", async () => {
    const api = serve();
    api.on("PUT /admin/profiles/2", (body: unknown) => ({ body: profile(body as object) }));
    renderApp("/admin/people");
    const card = within(await screen.findByRole("region", { name: "Nolan" }));
    await userEvent.click(card.getByRole("button", { name: "Edit" }));
    const spellings = card.getByLabelText(/Spellings/);
    await userEvent.clear(spellings);
    await userEvent.type(spellings, "Nolan, Nolen, Nolin");
    await userEvent.click(card.getByRole("button", { name: "Save" }));
    const put = api.sent.find((r) => r.method === "PUT");
    expect(put?.body).toEqual({ display_name: "Nolan", variants: ["Nolan", "Nolen", "Nolin"] });
  });

  it("deletes a person only after confirming", async () => {
    const api = serve();
    api.on("DELETE /admin/profiles/2", { deleted: true });
    renderApp("/admin/people");
    const card = within(await screen.findByRole("region", { name: "Nolan" }));
    await userEvent.click(card.getByRole("button", { name: "Delete" }));
    expect(api.sent.some((r) => r.method === "DELETE")).toBe(false);
    await userEvent.click(card.getByRole("button", { name: "Delete Nolan" }));
    expect(api.sent.some((r) => r.method === "DELETE" && r.path === "/admin/profiles/2")).toBe(true);
  });
});
