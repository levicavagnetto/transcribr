import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { type CallListItem, REFRESH_MS, type Status } from "../api/hooks";
import { attribution, auth, call, callList, type FakeApi, installFakeApi, people, status } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";
import { searchFilter } from "./Calls";

const TODAY = call(); // Today 11:41, transcribed
const MISSED = call({
  id: 90012402,
  start_local: "2026-10-21 08:03:00",
  start_utc: "2026-10-21T13:03:00Z",
  minutes: 3.5,
  caller_number: "(405) 555-0176",
  state: "not_transcribed",
  has_transcript: false,
});
const SILENT = call({ id: 90012413, start_local: "2026-10-22 09:47:00", minutes: 0.5167, no_speech: true });

interface World {
  api: FakeApi;
  calls: CallListItem[];
  status: Status;
}

function serve(calls: CallListItem[] = [TODAY, SILENT, MISSED], statusOverrides: Partial<Status> = {}): World {
  const world: World = { api: installFakeApi(), calls, status: status(statusOverrides) };
  world.api.on("GET /status", () => ({ body: world.status }));
  world.api.on("GET /auth/state", auth("login_required"));
  world.api.on("GET /calls", (_body: unknown, query: URLSearchParams) => {
    const wanted = query.get("state");
    return { body: callList(world.calls.filter((c) => !wanted || c.state === wanted)) };
  });
  return world;
}

function callsRequests(world: World): URLSearchParams[] {
  return world.api.sent.filter((r) => r.method === "GET" && r.path === "/calls").map((r) => r.query);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 22, 18, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the call list", () => {
  it("shows every call newest first with its details and state", async () => {
    serve();
    renderApp("/");
    const row = (await screen.findByRole("link", { name: "Today 11:41" })).closest("tr")!;
    const cells = within(row);
    expect(cells.getByText("4:37")).toBeInTheDocument();
    expect(cells.getByText("(405) 555-0187")).toBeInTheDocument();
    expect(cells.getByText("SW Counter Sales")).toBeInTheDocument();
    expect(cells.getByText("Transcribed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Today 11:41" })).toHaveAttribute("href", "/calls/90012417");
    const links = screen.getAllByRole("link", { name: /Today|Yesterday/ }).map((l) => l.textContent);
    expect(links).toEqual(["Today 11:41", "Today 9:47", "Yesterday 8:03"]);
    expect(within(screen.getByRole("link", { name: "Today 9:47" }).closest("tr")!).getByText("No speech")).toBeInTheDocument();
  });

  it("offers Transcribe on a missed call and sends it", async () => {
    const world = serve();
    world.api.on("POST /calls/90012402/transcribe", { queued: true, state: "waiting" });
    renderApp("/");
    const row = (await screen.findByRole("link", { name: "Yesterday 8:03" })).closest("tr")!;
    expect(within(row).getByText("Ended while Transcribr was off")).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: /Transcribe/ }));
    await vi.waitFor(() => {
      const post = world.api.sent.find((r) => r.path === "/calls/90012402/transcribe");
      expect(post?.headers["X-Transcribr"]).toBe("1");
    });
    expect(within(screen.getByRole("link", { name: "Today 11:41" }).closest("tr")!).queryByRole("button")).toBeNull();
  });

  it("filters by state and dates together", async () => {
    const world = serve();
    renderApp("/");
    await screen.findByRole("link", { name: "Today 11:41" });
    await userEvent.click(screen.getByRole("button", { name: "Not transcribed" }));
    expect(screen.getByRole("button", { name: "Not transcribed" })).toHaveAttribute("aria-pressed", "true");
    await vi.waitFor(() => expect(screen.queryByRole("link", { name: "Today 11:41" })).toBeNull());
    expect(screen.getByRole("link", { name: "Yesterday 8:03" })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("From"), "2026-10-20");
    await vi.waitFor(() => {
      const last = callsRequests(world).at(-1)!;
      expect([last.get("state"), last.get("from")]).toEqual(["not_transcribed", "2026-10-20"]);
    });
    await userEvent.click(screen.getByRole("button", { name: "Clear search and filters" }));
    await vi.waitFor(() => expect(callsRequests(world).at(-1)!.toString()).toBe("limit=50"));
  });

  it("searches words and shows the matching passage highlighted", async () => {
    const world = serve();
    renderApp("/");
    await screen.findByRole("link", { name: "Today 11:41" });
    world.calls = [
      call({
        passage: {
          at_s: 65,
          parts: [
            { text: "we want a ", hit: false },
            { text: "lift kit", hit: true },
            { text: " for a Tacoma", hit: false },
          ],
        },
      }),
    ];
    await userEvent.type(screen.getByLabelText("Search words said, or a phone number"), "lift kit");
    const hit = await screen.findByText("lift kit", { selector: "mark" });
    expect(hit.closest("td")).toHaveTextContent("at 1:05“we want a lift kit for a Tacoma”");
    expect(callsRequests(world).at(-1)!.get("q")).toBe("lift kit");
    expect(screen.getByText("1 call matches")).toBeInTheDocument();
  });

  it("sends a phone number as a number search", async () => {
    const world = serve();
    renderApp("/");
    await screen.findByRole("link", { name: "Today 11:41" });
    await userEvent.type(screen.getByLabelText("Search words said, or a phone number"), "(405) 555-0142");
    await vi.waitFor(() => expect(callsRequests(world).at(-1)!.get("number")).toBe("(405) 555-0142"));
    expect(callsRequests(world).at(-1)!.get("q")).toBeNull();
  });

  it("says when nothing matches", async () => {
    const world = serve();
    renderApp("/");
    await screen.findByRole("link", { name: "Today 11:41" });
    world.calls = [];
    await userEvent.type(screen.getByLabelText("Search words said, or a phone number"), "zebra");
    expect(await screen.findByText("No calls match")).toBeInTheDocument();
  });

  it("loads older calls with the cursor", async () => {
    const world = serve();
    world.api.on("GET /calls", (_body: unknown, query: URLSearchParams) =>
      query.get("cursor") === "page-2" ? { body: callList([MISSED]) } : { body: callList([TODAY], "page-2") },
    );
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Show older calls" }));
    expect(await screen.findByRole("link", { name: "Yesterday 8:03" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Today 11:41" })).toBeInTheDocument();
  });

  it("offers to list the week before at the end of the list", async () => {
    const world = serve();
    world.api.on("POST /calls/load-earlier", { requested: true });
    renderApp("/");
    expect(await screen.findByText(/oldest is from Yesterday 8:03/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "List the week before from Ravon" }));
    expect(await screen.findByText(/Asked the worker to list the week before/)).toBeInTheDocument();
    expect(world.api.sent.some((r) => r.method === "POST" && r.path === "/calls/load-earlier")).toBe(true);
  });

  it("points to first-time setup when there is no admin", async () => {
    serve([], { admin_exists: false, queues_chosen: false });
    renderApp("/");
    expect(await screen.findByText(/First-time setup/)).toBeInTheDocument();
  });

  it("says no calls are collected until a queue is chosen", async () => {
    serve([], { queues_chosen: false });
    renderApp("/");
    expect(await screen.findByText(/No store queues are chosen yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "/admin/settings" })).toHaveAttribute("href", "/admin/settings");
    expect(screen.getByText("No calls are listed yet.")).toBeInTheDocument();
  });

  it("says when the server can't be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    renderApp("/");
    expect((await screen.findAllByText(/Can't reach the Transcribr server/)).length).toBeGreaterThan(0);
  });
});

describe("the People filter", () => {
  const NOLANS = call({ id: 90012420, attributions: [attribution()] });
  const MAYBE = call({
    id: 90012421,
    start_local: "2026-10-22 10:15:00",
    attributions: [attribution({ status: "maybe", method: "voice", name_heard: null, name_at_s: null, voice_score: 0.58 })],
  });

  function servePeople(): World {
    const world = serve([NOLANS, MAYBE, MISSED]);
    world.api.on("GET /people", people());
    return world;
  }

  it("lists each person, Maybe and Unassigned with their counts", async () => {
    servePeople();
    renderApp("/");
    const group = await screen.findByRole("group", { name: "People" });
    const labels = within(group).getAllByRole("button").map((b) => b.textContent);
    expect(labels).toEqual(["Anyone", "Nolan (14)", "Dana (6)", "Maybe (3)", "Unassigned (9)"]);
  });

  it("shows people on each row, with Maybe marked differently", async () => {
    servePeople();
    renderApp("/");
    const table = within(await screen.findByRole("table"));
    expect(await table.findByLabelText("Nolan")).toHaveTextContent("Nolan");
    expect(table.getByLabelText("Maybe Nolan")).toHaveTextContent("Nolan?");
  });

  it.each([
    ["Nolan (14)", "person", "2"],
    ["Maybe (3)", "maybe", "true"],
    ["Unassigned (9)", "unassigned", "true"],
  ])("sends the %s filter", async (button, key, value) => {
    const world = servePeople();
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: button }));
    await vi.waitFor(() => expect(callsRequests(world).at(-1)!.get(key)).toBe(value));
  });

  it("combines a person with a search", async () => {
    const world = servePeople();
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Nolan (14)" }));
    await userEvent.type(screen.getByLabelText(/Search words said/), "lift kit");
    await vi.waitFor(() => {
      const last = callsRequests(world).at(-1)!;
      expect([last.get("person"), last.get("q")]).toEqual(["2", "lift kit"]);
    });
    await userEvent.click(screen.getByRole("button", { name: "Clear search and filters" }));
    await vi.waitFor(() => expect(callsRequests(world).at(-1)!.toString()).toBe("limit=50"));
  });

  it("is hidden while there are no people", async () => {
    const world = serve();
    world.api.on("GET /people", people({ people: [] }));
    renderApp("/");
    await screen.findByRole("link", { name: "Today 11:41" });
    expect(screen.queryByRole("group", { name: "People" })).toBeNull();
  });
});

describe("Check Ravon now", () => {
  it("asks the worker, then marks the calls it found as new", async () => {
    const world = serve([TODAY]);
    const fresh = call({ id: 90012420, start_local: "2026-10-22 12:03:00", state: "waiting", has_transcript: false });
    world.api.on("POST /check-ravon", () => {
      const reply = { requested: true, last_poll_ok: world.status.last_poll_ok };
      world.status = { ...world.status, last_poll_ok: "2026-10-22T17:03:30Z" }; // the worker polls
      world.calls = [fresh, TODAY];
      return { body: reply };
    });
    renderApp("/");
    await screen.findByRole("link", { name: "Today 11:41" });
    await userEvent.click(screen.getByRole("button", { name: "Check Ravon now" }));
    expect(await screen.findByRole("button", { name: "Checking Ravon…" })).toBeDisabled();
    expect(await screen.findByText("1 new call found.", {}, { timeout: 5000 })).toBeInTheDocument();
    const row = screen.getByRole("link", { name: "Today 12:03" }).closest("tr")!;
    expect(within(row).getByText("New")).toBeInTheDocument();
    expect(within(screen.getByRole("link", { name: "Today 11:41" }).closest("tr")!).queryByText("New")).toBeNull();
    expect(screen.getByRole("button", { name: "Check Ravon now" })).toBeEnabled();
    expect(world.api.sent.find((r) => r.path === "/check-ravon")?.headers["X-Transcribr"]).toBe("1");
  });

  it("says it waits for the call being transcribed", async () => {
    const world = serve([call({ state: "processing", has_transcript: false })]);
    world.api.on("POST /check-ravon", { requested: true, last_poll_ok: world.status.last_poll_ok });
    renderApp("/");
    await screen.findByRole("link", { name: "Today 11:41" });
    await userEvent.click(screen.getByRole("button", { name: "Check Ravon now" }));
    expect(await screen.findByRole("button", { name: "Waiting for the current call…" })).toBeDisabled();
    expect(screen.getByText(/checks Ravon as soon as it's done/)).toBeInTheDocument();
  });

  it("is disabled while the worker is stopped", async () => {
    serve([TODAY], { worker_running: false });
    renderApp("/");
    await screen.findByRole("link", { name: "Today 11:41" });
    expect(await screen.findByText("The worker isn't running, so Ravon can't be checked.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check Ravon now" })).toBeDisabled();
  });
});

describe("live updates", () => {
  it("shows a new call and a finished transcription within one refresh", async () => {
    vi.useRealTimers();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 9, 22, 18, 0));
    const world = serve([call({ state: "waiting", has_transcript: false })]);
    renderApp("/");
    const first = await screen.findByRole("link", { name: "Today 11:41" });
    expect(within(first.closest("tr")!).getByText("Waiting")).toBeInTheDocument();

    world.calls = [call({ id: 90012421, start_local: "2026-10-22 12:10:00" }), call()];
    await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS));

    expect(await screen.findByRole("link", { name: "Today 12:10" })).toBeInTheDocument();
    expect(within(screen.getByRole("link", { name: "Today 11:41" }).closest("tr")!).getByText("Transcribed")).toBeInTheDocument();
  });
});

describe("search box", () => {
  it.each([
    ["lift kit", { q: "lift kit" }],
    ["555-0142", { number: "555-0142" }],
    ["(405) 555 0142", { number: "(405) 555 0142" }],
    ["F-150", { q: "F-150" }],
    ["12", {}],
    ["  ", {}],
  ])("treats %j as %j", (text, expected) => {
    expect(searchFilter(text)).toEqual(expected);
  });
});
