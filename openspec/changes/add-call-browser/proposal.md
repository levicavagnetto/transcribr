# Proposal

## Why

After `add-call-transcription-core`, the instance collects and transcribes the store's calls, but staff can't see them. The service writer needs to find a call ("the lift kit guy from Tuesday"), read what was said, and hand it to ChatGPT for research, without scrolling through Ravon and re-listening.

## What Changes

- **Call list** replaces the core change's status home page. It shows every listed call, newest first: time, length, caller number, answered-by text and processing state. It filters by processing state and date range, and searches transcript words and caller numbers. Transcribe buttons appear on calls missed while the server was off.
- **Call detail:** the call's details and its speaker-labeled transcript with timestamps. It has Listen (the recording streamed from Ravon through the server, never saved), Transcribe/Retry, and the failure reason for Failed calls.
- **Copy for ChatGPT:** one click copies a research prompt, the call's details (phone number only if the user asks) and the transcript. It works on the plain-HTTP shop network.
- **Research prompt setting:** the admin edits the prompt in the admin Settings screen.
- **Live updates:** the list and the open call reflect new calls and state changes within 30 seconds.
- The collection figures from the core change's home page move into the status area of the app bar.
- **Out of scope:** people, attribution chips, person filters and attribution actions all come with `add-call-attribution`.

## Capabilities

### New Capabilities
- `call-browser`: the staff call screens and their API. Covers the call list with filters and search, call detail with the transcript, Listen, transcribe and retry, Copy for ChatGPT, and live updates.

### Modified Capabilities
- `instance-settings`: adds a requirement for the research-prompt setting.
- `web-app`: removes "Collection status on the home page", because the call list becomes the home page. The figures move to the status area.

## Impact

- **Backend:** new read endpoints for the call list, call detail and transcript (full-text search, cursor paging), a streaming audio endpoint, and a new setting. No schema change beyond what the core change creates: the FTS index and transcript tables already exist.
- **Frontend:** the Calls and Call views, the copy helper with clipboard fallbacks, and a new section on the Settings screen.
- **Ravon:** one extra GET per Listen, through the same allow list.
- **Depends on:** `add-call-transcription-core`, archived or at least implemented first.
