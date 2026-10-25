// Copy for ChatGPT (design D4): the text, and getting it onto the clipboard on plain-HTTP pages.

import type { CallDetail, Segment } from "./api/hooks";
import { fullDate, longLength, mss, startClock } from "./format";

export function chatGptText(
  prompt: string,
  call: CallDetail,
  segments: Segment[],
  includePhone: boolean,
): string {
  const header = [`Call: ${fullDate(call.start_local)}, ${startClock(call.start_local)}, ${longLength(call.minutes)}`];
  if (includePhone) header.push(`Caller: ${call.caller_number}`);
  const lines = segments.map((s) => `[${mss(s.start_s)}] ${s.speaker}: ${s.text}`);
  return [prompt.trim(), header.join("\n"), lines.join("\n")].join("\n\n");
}

export type CopyResult = "clipboard" | "execCommand" | "manual";

// The Clipboard API only works over HTTPS or on localhost, and the shop serves the app over plain
// HTTP. So: the Clipboard API if it works, else the older execCommand("copy") on a hidden textarea,
// else "manual", which means the caller shows the text selected for Ctrl+C.
export async function copyToClipboard(text: string): Promise<CopyResult> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return "clipboard";
    }
  } catch {
    // fall through to the older way
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let copied = false;
  try {
    copied = typeof document.execCommand === "function" && document.execCommand("copy");
  } catch {
    copied = false;
  }
  area.remove();
  return copied ? "execCommand" : "manual";
}
