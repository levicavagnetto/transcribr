import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { type CallDetail, REFRESH_MS } from "../api/hooks";
import { chatGptText } from "../copy";
import {
  auth,
  callDetail,
  DEFAULT_PROMPT,
  type FakeApi,
  installFakeApi,
  status,
  transcript,
} from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

const ID = 90012417;

function serve(detail: Partial<CallDetail> = {}): { api: FakeApi; detail: CallDetail } {
  const world = { api: installFakeApi(), detail: callDetail(detail) };
  world.api.on("GET /status", status());
  world.api.on("GET /auth/state", auth("login_required"));
  world.api.on(`GET /calls/${ID}`, () => ({ body: world.detail }));
  world.api.on(`GET /calls/${ID}/transcript`, transcript());
  world.api.on("GET /research-prompt", { prompt: DEFAULT_PROMPT });
  return world;
}

function setClipboard(writeText: ((text: string) => Promise<void>) | undefined) {
  Object.defineProperty(navigator, "clipboard", { value: writeText ? { writeText } : undefined, configurable: true });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 22, 18, 0));
});

afterEach(() => {
  vi.useRealTimers();
  setClipboard(undefined);
});

describe("a transcribed call", () => {
  it("shows its details and the transcript as timestamped lines without speakers", async () => {
    serve();
    renderApp(`/calls/${ID}`);
    expect(await screen.findByRole("heading", { name: "Today 11:41 · 4 min 37 s" })).toBeInTheDocument();
    const details = within(screen.getByRole("region", { name: "Call details" }));
    expect(details.getByText("Thu Oct 22 2026")).toBeInTheDocument();
    expect(details.getByText("(405) 555-0187")).toBeInTheDocument();
    expect(details.getByText("SW Counter Sales")).toBeInTheDocument();
    expect(details.getByText("Stillwater Sales/CS (x600)")).toBeInTheDocument();
    expect(details.getByText(/^Automatically, /)).toBeInTheDocument();
    expect(details.getByText("Transcribed", { selector: ".MuiChip-label" })).toBeInTheDocument();

    const lines = within(await screen.findByRole("region", { name: "Transcript" }));
    expect(lines.getByText("I need tires for my 2019 Silverado.")).toBeInTheDocument();
    expect(lines.getByText("1:05")).toBeInTheDocument();
    expect(lines.getByText("3 lines · small.en")).toBeInTheDocument();
    expect(lines.queryByText(/Speaker \d/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All calls" })).toHaveAttribute("href", "/");
  });

  it("says when it was transcribed on request", async () => {
    serve({ auto_queued: false });
    renderApp(`/calls/${ID}`);
    expect(await screen.findByText(/^On request, /)).toBeInTheDocument();
  });

  it("previews exactly what gets copied, with the number only when ticked", async () => {
    serve();
    renderApp(`/calls/${ID}`);
    const preview = await screen.findByTestId("copy-preview-text");
    expect(preview.textContent).toBe(chatGptText(DEFAULT_PROMPT, callDetail(), transcript().segments, false));
    expect(preview).not.toHaveTextContent("555-0187");

    await userEvent.click(screen.getByRole("checkbox", { name: "Include the phone number" }));
    expect(screen.getByTestId("copy-preview-text").textContent).toBe(
      chatGptText(DEFAULT_PROMPT, callDetail(), transcript().segments, true),
    );

    await userEvent.click(screen.getByRole("button", { name: "Hide what gets copied" }));
    expect(screen.queryByTestId("copy-preview-text")).toBeNull();
    expect(screen.getByRole("button", { name: "Show what gets copied" })).toHaveAttribute("aria-expanded", "false");
  });

  it("copies the previewed text and confirms", async () => {
    serve();
    const writeText = vi.fn(() => Promise.resolve());
    renderApp(`/calls/${ID}`);
    await screen.findByTestId("copy-preview-text");
    setClipboard(writeText); // after render: user-event installs its own clipboard on setup
    await userEvent.click(screen.getByRole("checkbox", { name: "Include the phone number" }));
    fireEvent.click(screen.getByRole("button", { name: "Copy for ChatGPT" }));
    expect(await screen.findByText(/Copied for ChatGPT, with the phone number/)).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(chatGptText(DEFAULT_PROMPT, callDetail(), transcript().segments, true));
  });

  it("shows the text selected when the browser blocks copying", async () => {
    serve();
    const execCommand = document.execCommand;
    document.execCommand = vi.fn(() => false);
    try {
      renderApp(`/calls/${ID}`);
      await screen.findByTestId("copy-preview-text");
      setClipboard(() => Promise.reject(new Error("NotAllowedError")));
      fireEvent.click(screen.getByRole("button", { name: "Copy for ChatGPT" }));
      const dialog = within(await screen.findByRole("dialog"));
      expect(dialog.getByText(/press Ctrl\+C/)).toBeInTheDocument();
      expect(dialog.getByLabelText("Text for ChatGPT")).toHaveValue(
        chatGptText(DEFAULT_PROMPT, callDetail(), transcript().segments, false),
      );
    } finally {
      document.execCommand = execCommand;
    }
  });

  it("plays through the server, and says when Ravon can't supply the recording", async () => {
    serve();
    renderApp(`/calls/${ID}`);
    const listen = within(await screen.findByRole("region", { name: "Listen" }));
    const audio = document.querySelector("audio")!;
    expect(audio).toHaveAttribute("src", `/api/v1/calls/${ID}/audio`);
    expect(audio).toHaveAttribute("preload", "none");
    fireEvent.error(audio);
    expect(listen.getByText(/can't be fetched from Ravon right now/)).toBeInTheDocument();
  });
});

describe("a call in other states", () => {
  it("offers Transcribe for a missed call", async () => {
    const world = serve({ state: "not_transcribed", has_transcript: false, transcribed_at: null, auto_queued: false });
    world.api.on(`POST /calls/${ID}/transcribe`, () => {
      world.detail = { ...world.detail, state: "waiting" };
      return { body: { queued: true, state: "waiting" } };
    });
    renderApp(`/calls/${ID}`);
    expect(await screen.findByText(/ended while Transcribr was off/)).toBeInTheDocument();
    expect(screen.getByText("Not yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Transcribe" }));
    expect(await screen.findByText(/Waiting to be transcribed/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy for ChatGPT" })).toBeNull();
  });

  it("shows why a call failed and offers Retry", async () => {
    const world = serve({
      state: "failed",
      has_transcript: false,
      transcribed_at: null,
      failure_reason: "The recording from Ravon was incomplete.",
    });
    world.api.on(`POST /calls/${ID}/transcribe`, { queued: true, state: "waiting" });
    renderApp(`/calls/${ID}`);
    expect(await screen.findByText("The recording from Ravon was incomplete.", { exact: false })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await vi.waitFor(() => expect(world.api.sent.some((r) => r.path === `/calls/${ID}/transcribe`)).toBe(true));
  });

  it("says a no-speech call had nothing to transcribe", async () => {
    serve({ no_speech: true });
    renderApp(`/calls/${ID}`);
    expect(await screen.findByText(/no recognizable speech/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy for ChatGPT" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Transcript" })).toBeNull();
  });

  it("says a processing call is being transcribed", async () => {
    serve({ state: "processing", has_transcript: false, transcribed_at: null });
    renderApp(`/calls/${ID}`);
    expect(await screen.findByText(/Transcribing… The transcript appears here when it's done./)).toBeInTheDocument();
  });

  it("explains an unknown call", async () => {
    const world = serve();
    world.api.on(`GET /calls/${ID}`, () => ({
      status: 404,
      body: { error: { code: "call_not_found", message: `No call ${ID} is listed.` } },
    }));
    renderApp(`/calls/${ID}`);
    expect(await screen.findByText(`No call ${ID} is listed.`)).toBeInTheDocument();
  });
});

describe("live updates on the call page", () => {
  it("shows the transcript within one refresh after it finishes", async () => {
    vi.useRealTimers();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 9, 22, 18, 0));
    const world = serve({ state: "processing", has_transcript: false, transcribed_at: null });
    renderApp(`/calls/${ID}`);
    await screen.findByText(/Transcribing…/);

    world.detail = callDetail();
    await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS));

    expect(await screen.findByText("I need tires for my 2019 Silverado.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy for ChatGPT" })).toBeInTheDocument();
  });
});

it("falls back to the queue's Ravon value until the worker has read the queue names", async () => {
  serve({ queue_label: null });
  renderApp(`/calls/${ID}`);
  expect(await screen.findByText("tireProz-salescustserv")).toBeInTheDocument();
});
