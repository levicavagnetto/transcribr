# Tasks

## 1. Call API

- [ ] 1.1 Store a digits-only copy of each caller number when calls are listed (a small migration plus a backfill of existing rows), and verify a migration test and a listing test
- [ ] 1.2 Implement `GET /api/v1/calls` with state and date filters, cursor paging (design D1) and stable pages while new calls arrive; verify tests for each filter, combined filters, and paging across an insert
- [ ] 1.3 Add text search (FTS5 phrase match, `snippet()` with highlights, the matched segment's time) and number search (digits-only suffix match); verify tests for every scenario under "Text and number search"
- [ ] 1.4 Implement `GET /api/v1/calls/{id}` and `GET /api/v1/calls/{id}/transcript` with response models that have no fingerprint fields; verify tests for each call state, including "no speech", and a test that no response contains fingerprint data
- [ ] 1.5 Implement `GET /api/v1/calls/{id}/audio` streaming through `web`'s guarded client (design D3) with a 502 on Ravon errors; verify tests against the fake Ravon for success, Ravon down, and no audio left on disk
- [ ] 1.6 Add the `research_prompt` setting (design D5) with its default and the 1–4,000 character rule, exposed through the admin settings endpoints; verify tests for the default, editing, and rejecting an empty prompt
- [ ] 1.7 Extend the GET-purity and OpenAPI tests from the core change to cover the new routes, with the audio route as the one documented Ravon exception
- [ ] 1.8 Implement `POST /api/v1/check-ravon` and the worker side (design D7); verify tests that a request causes a check within one worker loop, that two requests within 15 s cause one search, and that a request made during a job is handled right after it

## 2. Calls and Call screens

- [ ] 2.1 Build the Calls view at `/` (table, status and date filters, search field with highlighted passages, Transcribe on Not transcribed rows, infinite scroll, the first-setup notice), and move the collection figures into the app bar status chip; verify component tests for filtering, combined filters, search results and Transcribe
- [ ] 2.2 Build the Call view at `/calls/:id` (details chips, the transcript with timestamps and speaker labels, Listen, Transcribe and Retry with the failure reason, the "no speech" message); verify component tests for each call state and the Listen error message
- [ ] 2.3 Implement the copy helper and Copy for ChatGPT (design D4: text format, include-phone-number switch, the three-step fallback, a confirmation snackbar); verify unit tests for the exact copied text with and without the number, and for each fallback step when the previous one is unavailable
- [ ] 2.4 Add the research prompt section to the admin Settings screen, and verify component tests for editing and the empty-prompt message
- [ ] 2.5 Verify live updates with a component test using fake timers: a new call appears and a Waiting call becomes Transcribed within one refetch interval
- [ ] 2.6 Add the Check Ravon now button to the Calls view (design D7); verify component tests for sending the request, "Checking…" until the last check changes, the list refreshing, the busy message, and the disabled state when the worker is stopped

## 3. End-to-end checks

- [ ] 3.1 Extend the compose smoke test: a listed call is found by a transcript phrase and by its number; its detail shows the transcript; Listen returns audio; Copy for ChatGPT text matches the expected format; a missed call is transcribed from its Transcribe button; with the poll interval at 30 minutes, Check Ravon now lists a new call within seconds; verify that it passes in the `check` script
- [ ] 3.2 With the user, on the shop PC against real Ravon: find a recent call by a phrase they remember, listen to it, copy it into ChatGPT, and record in the change notes whether the copied text was usable as is

## Workflow follow-up

- Run `/opsx:verify` before archiving.
- Archive with `/opsx:archive` after `add-call-transcription-core` has been archived.
