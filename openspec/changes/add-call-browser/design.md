# Design

## Context

See `proposal.md` for the motivation and `specs/` for the required behavior. This change builds on `add-call-transcription-core` and reuses its pieces unchanged:
- the SQLite schema, which already has calls, transcripts with segments and word timestamps, a transcript FTS5 index and speakers
- the guarded Ravon client
- the FastAPI app, with GET-pure reads and OpenAPI
- the MUI theme and app shell, including the status banner, the footer Admin link and the 10-second refetch
- the admin Settings screen, built to take more sections

Mockups: the design canvas at https://claude.ai/artifact/9WxKCnhBUmpG7UZKVH4MD1 (Calls, Call detail, other call states, the research prompt setting, and Calls in the dark theme), reviewed by the user on 2026-10-25. D6 records its layout.

## Goals / Non-Goals

**Goals:**
- Finding a call in seconds: by state, date, words said, or caller number.
- One-click handoff to ChatGPT that works on plain HTTP.
- No new storage: everything comes from tables the core change already fills.

**Non-Goals:**
- People, attribution chips, person filters, claim and reject actions, and "Speaker N is …" (`add-call-attribution`).
- Editing transcripts, exporting files, and any summary written by the app.
- WebSockets or server-sent events. The 10-second refetch already meets the 30-second live-update requirement.

## Decisions

### D1. Endpoints
- `GET /api/v1/calls` takes `state`, `from`, `to` (store time zone), `q` (text) and `number`, plus `cursor` and `limit` (default 50, max 200).
  - It returns rows newest first.
  - The cursor is an opaque, base64-encoded `(start_time, id)` of the last row, so pages stay stable while new calls arrive.
- `GET /api/v1/calls/{id}` returns the details and state.
- `GET /api/v1/calls/{id}/transcript` returns the segments with speaker labels and timestamps.
- `GET /api/v1/calls/{id}/audio` streams from Ravon. It's the one GET documented as reaching Ravon, as the `web-app` REST rule allows.
- `POST /api/v1/calls/{id}/transcribe` (from the core change) covers both Transcribe and Retry.
- `POST /api/v1/check-ravon` asks the worker to check Ravon now (D7).
- Fingerprints are excluded at the response-schema level: the Pydantic models have no field for them, so they can't leak by accident.

### D2. Search
- **Text:** an FTS5 `MATCH` on the transcript index, with the user's words quoted as a phrase when they contain a space. FTS5 `snippet()` gives the matching passage with `<mark>` delimiters, which the UI renders as highlights without using raw HTML. The matched segment's start time comes from a join on the segment rowid.
- **Number:** digits only on both sides, compared as a suffix match, so "555-0142" finds "(405) 555-0142". The digits-only column is stored when the call is listed.
- **Why FTS5:** it's built into SQLite, fast at this volume (thousands of calls), and needs no extra service. The alternative, `LIKE` scans, is slower and has no ranking or snippets.

### D3. Listen
- The `web` service streams the MP3 from Ravon to the browser chunk by chunk, using `web`'s own guarded client, with no disk buffer.
- `Content-Type` is `audio/mpeg`. `Content-Length` is passed through when Ravon sends it, so the browser's player can show the duration.
- Range requests aren't supported in this change. The player plays from the start, and calls are short (2.5 minutes on average).
- Errors map to a 502 with a plain message, which the UI shows.
- **Alternative:** a redirect to Ravon. The browser has no Ravon session, so it gets a 401.

### D4. Copy for ChatGPT
- The browser Clipboard API only works over HTTPS or on localhost, and the app is served as `http://<pc>:<port>` on the shop network.
- The copy helper tries three things in order:
  1. `navigator.clipboard.writeText` when it exists and resolves
  2. a hidden textarea with `document.execCommand('copy')`
  3. a dialog with the text pre-selected, for Ctrl+C
- **The copied text:** the prompt, a blank line, then `Call: Tue Oct 22 2026, 10:42, 6 min 12 s` (plus `Caller: …` only when the switch is on), a blank line, then one `[m:ss] Speaker: text` line per segment.
- **Alternative:** HTTPS with a self-signed certificate. Browsers would show warnings on every device.

### D5. Research prompt setting
- A new `research_prompt` key in the settings registry from the core change, validated as 1 to 4,000 characters.
- It gets its own section on the admin Settings screen.
- The default text is the one in the mockup.

### D6. UI structure
- **Views:** `/` (Calls) and `/calls/:id` (Call), both under the core change's app shell.
- **Calls header:** the title, then "Last check hh:mm · every N min" with Check Ravon now at the right and a status line under the button ("Checking Ravon…", "1 new call found.", or why it can't check).
- **Filter panel:** a search field (words or a phone number), the state as toggle buttons (Any, Transcribed, Waiting, Processing, Not transcribed, Failed), and From/To date fields. A "Clear search and filters" link appears when any is set.
- **Table:** an MUI `Table` with infinite scroll from the cursor. Columns: Started (links to the call), Length, Caller, Answered by, State, and a notes column showing "New", "No speech", or "Ended while Transcribr was off" with a Transcribe button. A search hit adds a second line to its row: "at m:ss" and the passage with the matched words highlighted. The end of the list has "List the week before from Ravon" (the core change's load-earlier action).
- **Status area:** the last-check and Waiting/Failed figures from the old home page move into a compact status chip in the app bar: "N waiting · N failed today".
- **Call:** a header (start time and length, state chip) and a details grid (caller, answered by, queue, how and when transcribed); an actions row with Copy for ChatGPT, "Include the phone number", and "Show/Hide what gets copied" (open by default, showing the exact text); a Listen bar using the native `<audio>` element styled with theme tokens; then the transcript as rows of time, speaker with a colour dot, and text.
- **Other states:** Not transcribed, Failed, No speech, and Waiting/Processing follow the canvas's "other states" board.
- **Data fetching:** TanStack Query keys per filter set, with a 10-second `refetchInterval` while the tab is visible.

### D7. Check Ravon now
- `POST /api/v1/check-ravon` is an open action with the usual `X-Transcribr: 1` header. It sets a `check_requested` flag in the service state. The web service never talks to Ravon for this; only the worker holds the Ravon session.
- The worker reads the flag on every loop: about once a second when idle, or right after a job finishes. If the last check was at least 15 seconds ago, it checks now and restarts its schedule from there. Either way it clears the flag.
- The UI notes the last check time when the button is pressed, shows "Checking…", and refetches the status every 2 seconds until that time changes. Then it refreshes the list. If Ravon reports an error, the button shows it; after 60 seconds it gives up with a message.
- **Alternative:** the web service checks Ravon itself. Rejected, because two services would then log in to Ravon and pace their requests separately.

## Risks / Trade-offs

- **Anyone on the shop network can read every call.** → The user chose this. Access rules can be added later without data changes.
- **FTS5's tokenizer won't match misspellings** ("Silverado" vs "Silverardo"). → Accepted for now. Trigram search is a later option.
- **Copying puts customer conversation text on the clipboard and into ChatGPT.** → The phone number is off by default. What happens in ChatGPT is the user's choice, as agreed.
- **No range requests means the player can't seek.** → Accepted for short calls. Range passthrough can be added if users ask.

## Migration Plan

Deploy by updating the image. No schema migration is needed, and the research prompt gets its default on first read.

Rollback: start the previous image. Nothing is lost, because this change adds no tables.
