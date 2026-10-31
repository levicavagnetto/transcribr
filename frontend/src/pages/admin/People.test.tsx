import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Profile, Samples } from "../../api/hooks";
import { auth, type FakeApi, installFakeApi, profile, status } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

const SAMPLES: Samples = {
  voice: profile().voice,
  calls: [
    {
      call_id: 90012417,
      start_local: "2026-10-22 11:41:00",
      seconds: 12,
      lines: [
        { idx: 0, start_s: 0, end_s: 3.5 },
        { idx: 2, start_s: 65, end_s: 73.5 },
      ],
    },
  ],
};

function serve(profiles: Profile[] = [profile()], samples: Samples = SAMPLES): FakeApi {
  const api = installFakeApi();
  api.on("GET /status", status());
  api.on("GET /auth/state", auth("logged_in"));
  api.on("GET /admin/profiles", { profiles });
  for (const p of profiles) api.on(`GET /admin/profiles/${p.id}/samples`, samples);
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

  it("lists each person with their name spellings, how calls were found and the consent note", async () => {
    serve();
    renderApp("/admin/people");
    const card = within(await screen.findByRole("region", { name: "Nolan" }));
    expect(card.getByText("Nolen")).toBeInTheDocument();
    expect(card.getByText(/11 by name · 0 by voice · 0 by name and voice · 3 by hand · 3 still Maybe/)).toBeInTheDocument();
    expect(screen.getByText(/knows about it and agrees/)).toBeInTheDocument();
  });

  it("says how much more is needed before voice matching starts", async () => {
    serve();
    renderApp("/admin/people");
    expect(
      await screen.findByText("Voice matching is off: 2 of 3 calls, 20 s of 30 s. Needs 1 more call and 10 s more speech."),
    ).toBeInTheDocument();
  });

  it("says when voice matching is on", async () => {
    serve([profile({ voice: { calls: 4, seconds: 41, usable: true, calls_needed: 0, seconds_needed: 0 } })]);
    renderApp("/admin/people");
    expect(await screen.findByText("Voice matching is on (4 calls, 41 s enrolled).")).toBeInTheDocument();
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

  it("shows enrolled lines by call and removes a call's lines", async () => {
    const api = serve();
    api.on("DELETE /admin/profiles/2/samples/90012417", { ...SAMPLES, calls: [] });
    renderApp("/admin/people");
    const lines = within(await screen.findByRole("list", { name: "Enrolled lines for Nolan" }));
    expect(lines.getByText("2 lines · 12 s · 0:00, 1:05")).toBeInTheDocument();
    await userEvent.click(lines.getByRole("button", { name: /Remove the lines from/ }));
    expect(api.sent.some((r) => r.method === "DELETE" && r.path === "/admin/profiles/2/samples/90012417")).toBe(true);
  });
});
