# Tasks

## 1. Project scaffolding

- [x] 1.1 Create the backend project in `backend/` (Python 3.12, uv, package `transcribr`, the layout from design D14) with ruff, pyright and pytest configured; verify `uv run pytest` runs and reports zero tests collected without errors
- [x] 1.2 Create the frontend project in `frontend/` (Vite, React, TypeScript, MUI `@mui/material` with Emotion and `@mui/icons-material`, TanStack Query, React Router, Vitest), plus the custom theme in `src/theme.ts` matching the mockups; verify `npm run build` and `npm test` succeed on the empty app
- [x] 1.3 Add a root `.gitignore` that excludes `.env`, `*.har`, all audio extensions (except named test fixtures), instance data, databases, model files and build output, and verify `git check-ignore` reports each pattern as ignored for sample paths while `.env.example`, audio fixtures and the `openspec/` files stay tracked
- [x] 1.4 Add a `check` script that runs the linter, the type checker and both test suites, and verify it exits 0

## 2. Store, migrations and settings

- [ ] 2.1 Implement the SQLite connection helper (WAL mode, busy timeout, foreign keys) and the migration runner (numbered SQL files, `user_version`, a pre-migration backup, one transaction per migration); verify with tests for a fresh database, an upgrade, and a failing migration that leaves the data unchanged
- [ ] 2.2 Write the first migration (tables: calls, jobs, transcripts + FTS5, speakers, profiles, name variants, voice samples, attributions, settings, uptime spans, service state, admin, admin sessions, admin setup code), and verify a schema test that creates an empty database and checks every table and index
- [ ] 2.3 Implement typed settings with defaults and validation (queues, poll interval 1–30 minutes, time zone, research prompt, voice thresholds), and verify tests for the defaults, rejecting out-of-range values, and applying a change without a restart
- [ ] 2.4 Implement environment configuration (`RAVON_USERNAME`, `RAVON_PASSWORD`, `RAVON_BASE_URL`, `TRANSCRIBR_PORT`, `TRANSCRIBR_DATA_DIR`) plus log redaction, and verify a test that logs a record carrying credentials and cookies and finds none of them in the output

## 3. Ravon client and fake Ravon

- [ ] 3.1 Implement the allow-list guard (spec `ravon-ingest`: read-only request allow list, date-bounded searches), and verify unit tests for every allowed and refused case plus a property-based test comparing it with a plain reference implementation
- [ ] 3.2 Implement the httpx client with the guard as its transport, manual redirect checks, pacing, and backoff on consecutive failures; verify that a request bypassing the client's helpers is still refused, and that the backoff timing works with a fake clock
- [ ] 3.3 Implement login, session reuse, one re-login on expiry, and stop-on-rejected-credentials with the credential-hash reset; verify against the fake Ravon for the expired-session, rejected-login and retry-login scenarios
- [ ] 3.4 Implement the parsers for the queue `<select>` and the `DataTable({ data: [...] })` results (recording ID from the checkbox value), with a loud failure when the page format changes; verify with synthetic pages copying the real structure, including an empty result and a changed format
- [ ] 3.5 Implement the audio download into memory with a `Content-Length` check; verify that a truncated response fails, and that a test scanning the temp and data folders after downloads finds no audio files
- [ ] 3.6 Build `tests/fake_ravon/` (login, search page, search submit, recordings, controllable faults) and verify that the client test suite runs entirely against it with no network access
- [ ] 3.7 Write a `realsite`-marked smoke command (`transcribr ravon-check`) that logs in, lists the queues and counts one day's calls without downloading audio, and verify it with the user against the real site (the user runs it; record the queue count and call count in the change notes)

## 4. Ingest: poller, uptime and catch-up

- [ ] 4.1 Implement uptime spans from worker heartbeats (design D4), and verify tests for extending a span, starting a new span after a gap of more than 3 minutes, and the 2-minute grace
- [ ] 4.2 Implement the poll cycle (design D5: per-queue windows, inserts that ignore duplicate IDs, auto-queue only when the call's end falls inside a span), and verify tests for all scenarios under "Poll for new calls" and "Automatic transcription only for calls that ended while the server was running"
- [ ] 4.3 Implement the catch-up on start, the first-start 7-day listing, and "load earlier" in 7-day chunks; verify the restart-after-downtime, first-start and load-earlier scenarios against the fake Ravon
- [ ] 4.4 Implement the worker main loop (heartbeat, settings reread, poll schedule, job processing, graceful shutdown), and verify an integration test that runs the worker against the fake Ravon for a simulated hour with a fake clock

## 5. Processing pipeline

- [ ] 5.1 Add a script that generates the synthetic two-voice test clips (short, small, no real voices) and commit the clips; verify the tests can decode them
- [ ] 5.2 Implement audio decoding to 16 kHz mono float32 in memory (PyAV, `av<19` pin), and verify a test on the fixture clips with no temporary files created
- [ ] 5.3 Implement transcription with faster-whisper (`small.en`, int8, VAD, word timestamps, hotwords from profile name variants), and verify a `model`-marked test that transcribes a fixture clip and spells a hotword name as configured
- [ ] 5.4 Implement speaker separation and per-speaker fingerprints with sherpa-onnx (design D8), including splitting segments by word timestamps and the minimum-speech rules; verify a `model`-marked test that finds two speakers in the two-voice fixture and stores no audio
- [ ] 5.5 Implement the job runner (claim in a transaction, states, return `processing` to `waiting` on start, 3 attempts with backoff, Ravon-outage waits that don't use attempts, manual requests ignoring duplicates); verify tests for every scenario in the `call-transcription` spec except the model-dependent ones
- [ ] 5.6 Run the worker at low CPU priority and verify a test that `web` answers the call list within 2 seconds while a fixture backlog of 50 calls is processing (a `slow`-marked test)

## 6. Calibration on real calls

- [ ] 6.1 Add a `realsite` calibration command that processes a user-chosen list of recording IDs and writes speakers, speech seconds and pairwise fingerprint similarities to a local report, with no audio and no transcript text in the report; verify it runs on two fixture calls through the fake Ravon
- [ ] 6.2 With the user, run calibration on at least 10 calls known to include one service writer and at least 10 known not to include them; record the similarity spread, choose default low and high thresholds, and write them into the settings defaults with the numbers in the change notes
- [ ] 6.3 With the user, check from the same calls how often the service writer's name appears in the first 30 seconds of speech, and record the rate in the change notes

## 7. Attribution and profiles

- [ ] 7.1 Implement profiles and name variants (create, edit, delete, with cascade deletion of voice samples and automatic attributions); verify tests for the "People profiles" scenarios
- [ ] 7.2 Implement voice enrollment (add or remove a call's speaker, centroid rebuild, the 3-call / 60-second usability rule); verify tests for the "Voice enrollment from existing calls" scenarios
- [ ] 7.3 Implement name evidence (the first 30 seconds of speech, normalization, rapidfuzz ratio ≥ 88), and verify tests for the greeting, late-name and misspelling cases
- [ ] 7.4 Implement voice evidence and the attribution rules as pure functions, and verify table-driven tests for every scenario under "Automatic attribution rules", plus speaker naming
- [ ] 7.5 Implement manual attribution (claim with an optional speaker, reject, confirm Maybe, the offer to enroll the speaker), and verify that manual rows survive a rematch
- [ ] 7.6 Implement rematch jobs triggered by profile and threshold changes, using only stored data; verify that a rematch over 100 stored calls makes zero Ravon requests and changes no manual rows
- [ ] 7.7 Run attribution automatically after each successful transcription, and verify an integration test from a listed call to a Transcribed and attributed call against the fake Ravon

## 8. REST API

- [ ] 8.1 Implement the FastAPI app skeleton (`/api/v1`, error format, `/api/v1/health`, serving the built UI files with an SPA fallback); verify the health endpoint and static serving in tests
- [ ] 8.2 Implement the call list (filters for person, Unassigned, Maybe, state and date; cursor paging; FTS5 text search with highlights; digits-only phone search), and verify tests for every scenario under "Call list with filters" and "Text and number search"
- [ ] 8.3 Implement call detail, the transcript with speaker names, and the actions (transcribe or retry, claim, reject, confirm, enroll); verify the tests, and verify that no response includes fingerprint data
- [ ] 8.4 Implement the audio streaming endpoint through the web service's own guarded Ravon client, and verify a test that streams from the fake Ravon and leaves no audio on disk
- [ ] 8.5 Implement the admin-only profile and settings endpoints under `/api/v1/admin/` (profiles, name variants, enrolled-sample removal, settings, queue list from Ravon, retry login) and the open load-earlier and status endpoints; verify tests for the `instance-settings` scenarios, including "Password never exposed"
- [ ] 8.6 Implement admin access (design D13): the setup code on start while no admin exists, `/api/v1/admin/setup`, login, logout, password change, Argon2id hashing, hashed server-side sessions with 12-hour expiry, the `SameSite=Strict` cookie, the required `X-Transcribr-Admin` header on admin writes, and per-IP backoff; verify tests for every `admin-access` scenario
- [ ] 8.7 Add `transcribr reset-admin`, and verify a test that it removes the admin and sessions and prints a new working setup code
- [ ] 8.8 Add a test that walks the generated route list and asserts every `/api/v1/admin/` route rejects requests without a valid admin session, and that every non-admin call action (including "Speaker N is …") works without one
- [ ] 8.9 Add a test that calls every GET endpoint and asserts the database is unchanged and no Ravon request was made (except audio), plus a test that the generated OpenAPI document covers every route

## 9. Web UI

- [ ] 9.1 Build the app shell (navigation, with People and Settings links only for a logged-in admin; a footer with a small "Admin" link to `/admin`; the service status banner; the 10-second refetch), and verify Vitest tests that the banner renders for each status kind and that admin links are hidden without a session
- [ ] 9.2 Add the light and dark colour schemes (design D10, token tables in `docs/architecture.md`), `InitColorSchemeScript`, and the Light / Dark / System menu saved in browser storage; verify a unit test that computes the contrast of every text/background token pair in both schemes and fails below 4.5:1, plus a component test that the menu choice persists across a remount
- [ ] 9.3 Build the Calls view (list, filters, search with highlights, Transcribe buttons on Not transcribed calls, Maybe markers), and verify component tests for filtering, combining filters and Transcribe
- [ ] 9.4 Build the Call view (details, attributions, the transcript with speaker names, Listen, claim/reject/confirm, "Speaker N is …" enrollment, Retry for Failed), and verify component tests for each call state
- [ ] 9.5 Implement Copy for ChatGPT (prompt + details + transcript, the include-phone-number switch, the three-step clipboard fallback from design D10), and verify unit tests for the copied text and the fallback when `navigator.clipboard` is missing
- [ ] 9.6 Build the People view at `/admin/people` (create, edit or delete a profile, name variants, enrolled calls and seconds, "how much more is needed"), and verify component tests
- [ ] 9.7 Build the Settings view at `/admin/settings` (the queue picker read from Ravon, poll interval, time zone, research prompt, thresholds, validation messages, the first-setup prompt when no queue is chosen), and verify component tests including rejected values
- [ ] 9.8 Build the admin login, first-time setup (setup code, then username and password with the 12-character rule), log out, and change password screens; route any `/admin` page to login or setup when there is no session; verify component tests for each flow, including a wrong setup code and a short password

## 10. Status and operations

- [ ] 10.1 Implement the status report (worker heartbeat age, last successful poll, Ravon state, queue length, failures in the last 24 hours, allow-list violations), and verify tests for the healthy, worker-stopped, login-failed and unreachable states
- [ ] 10.2 Implement `transcribr worker-health` and `transcribr backup` (the SQLite backup API into `/data/backups`), and verify that the backup restores into a fresh data folder with identical counts
- [ ] 10.3 Implement structured logging to stdout and a rotating file under `/data/logs`, and verify that the redaction test from 2.4 also passes through both outputs

## 11. Packaging and deployment

- [ ] 11.1 Write the multi-stage Dockerfile (UI build, a model stage with pinned revisions and SHA-256 checks, a Python 3.12 slim runtime, non-root uid 10001), and verify `docker build` succeeds and `docker run --rm <image> id -u` prints 10001
- [ ] 11.2 Write `compose.yaml` (`web` and `worker` from one image, a named volume, `restart: unless-stopped`, health checks, the worker waiting for a healthy web, only the web port published) and `.env.example`; verify `docker compose up -d` gives two healthy services
- [ ] 11.3 Verify the no-runtime-downloads requirement by running the stack with outbound network restricted to the fake Ravon and processing a fixture call end to end
- [ ] 11.4 Build and run the arm64 image (buildx with emulation or an arm64 host), and verify that the fixture pipeline test passes inside it
- [ ] 11.5 Write the README (install on Linux, Windows with Docker Desktop and auto-start, and macOS; `.env`; first setup, including finding the admin setup code in `docker compose logs web` and `reset-admin`; profiles and the consent note; updating; backup and restore; troubleshooting the banner states), and verify by following it on a clean host to a working instance

## 12. End-to-end checks

- [ ] 12.1 Run a compose smoke test of web + worker + fake Ravon: a new call is auto-transcribed and attributed by name, a call during simulated downtime stays Not transcribed until Transcribe is clicked, Copy for ChatGPT text is produced, and the admin is created from the logged setup code, logs in and changes a setting; verify that it passes in the `check` script
- [ ] 12.2 Run the resilience checks: kill the worker mid-call, restart Docker, recreate the containers, and update to a rebuilt image with a no-op migration; verify that no call is lost, duplicated or stuck, and that data persists
- [ ] 12.3 With the user, run the instance against the real Ravon for one working day on the shop PC, then compare its call count with Ravon's search for the same day, check the service writer's calls under his filter, and record the results in the change notes

## Workflow follow-up

- Review the calibration and real-day results before archiving.
- Archive this change with `/opsx:archive` once all tasks are done, so its specs become the main specs.
- Start the follow-up change `add-mcp-server` (read-only MCP server as a client of the REST API, secure tunnel, OAuth, ChatGPT developer-mode connector test).
