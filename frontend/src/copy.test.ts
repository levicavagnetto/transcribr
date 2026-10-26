import { chatGptText, copyToClipboard } from "./copy";
import { callDetail, transcript } from "./test/fakeApi";

const PROMPT = "List what the customer asked for.";

describe("the text copied for ChatGPT", () => {
  it("is the prompt, the call details without the number, then the transcript", () => {
    expect(chatGptText(PROMPT, callDetail(), transcript().segments, false)).toBe(
      [
        "List what the customer asked for.",
        "",
        "Call: Thu Oct 22 2026, 11:41, 4 min 37 s",
        "",
        "[0:00] Thanks for calling, front counter.",
        "[0:04] I need tires for my 2019 Silverado.",
        "[1:05] About nine hundred for all four.",
      ].join("\n"),
    );
  });

  it("adds the caller number only when asked", () => {
    const text = chatGptText(PROMPT, callDetail(), transcript().segments, true);
    expect(text).toContain("Call: Thu Oct 22 2026, 11:41, 4 min 37 s\nCaller: (405) 555-0187\n\n[0:00]");
    expect(chatGptText(PROMPT, callDetail(), [], false)).not.toContain("555-0187");
  });
});

describe("copying to the clipboard", () => {
  const original = { clipboard: navigator.clipboard, execCommand: document.execCommand };

  afterEach(() => {
    Object.defineProperty(navigator, "clipboard", { value: original.clipboard, configurable: true });
    document.execCommand = original.execCommand;
  });

  function setClipboard(writeText: ((text: string) => Promise<void>) | undefined) {
    Object.defineProperty(navigator, "clipboard", {
      value: writeText ? { writeText } : undefined,
      configurable: true,
    });
  }

  it("uses the Clipboard API when it works", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    setClipboard(writeText);
    document.execCommand = vi.fn(() => true);
    expect(await copyToClipboard("hello")).toBe("clipboard");
    expect(writeText).toHaveBeenCalledWith("hello");
    expect(document.execCommand).not.toHaveBeenCalled();
  });

  it("falls back to execCommand when the Clipboard API is missing, as on plain HTTP", async () => {
    setClipboard(undefined);
    let selected = "";
    document.execCommand = vi.fn(() => {
      selected = document.querySelector("textarea")?.value ?? "";
      return true;
    });
    expect(await copyToClipboard("hello")).toBe("execCommand");
    expect(document.execCommand).toHaveBeenCalledWith("copy");
    expect(selected).toBe("hello");
    expect(document.querySelector("textarea")).toBeNull(); // cleaned up
  });

  it("falls back to execCommand when the Clipboard API refuses", async () => {
    setClipboard(() => Promise.reject(new Error("NotAllowedError")));
    document.execCommand = vi.fn(() => true);
    expect(await copyToClipboard("hello")).toBe("execCommand");
  });

  it("asks for a manual copy when both are refused", async () => {
    setClipboard(() => Promise.reject(new Error("NotAllowedError")));
    document.execCommand = vi.fn(() => false);
    expect(await copyToClipboard("hello")).toBe("manual");
  });

  it("asks for a manual copy when execCommand throws", async () => {
    setClipboard(undefined);
    document.execCommand = vi.fn(() => {
      throw new Error("not supported");
    });
    expect(await copyToClipboard("hello")).toBe("manual");
  });
});
