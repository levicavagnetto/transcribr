# Tasks

## 1. Project scaffolding

- [x] 1.1 Create the backend project in `backend/` (Python 3.14, uv, package `transcribr`, the layout from design D13) with ruff, pyright and pytest configured; verify `uv run pytest` passes a package smoke test (imports every package, runs the CLI)
- [x] 1.2 Create the frontend project in `frontend/` (Vite, React, TypeScript, MUI `@mui/material` with Emotion and `@mui/icons-material`, TanStack Query, React Router, Vitest), plus the custom theme in `src/theme.ts` matching the mockups; verify `npm run build` and `npm test` succeed on the empty app
- [x] 1.3 Add a root `.gitignore` that excludes `.env`, `*.har`, all audio extensions (except named test fixtures), instance data, databases, model files and build output, and verify `git check-ignore` reports each pattern as ignored for sample paths while `.env.example`, audio fixtures and the `openspec/` files stay tracked
- [x] 1.4 Add a `check` script that runs the linter, the type checker and both test suites, and verify it exits 0

## 2. Store, migrations and settings

- [x] 2.1 Implement the SQLite connection helper (WAL mode, busy timeout, foreign keys) and the migration runner (numbered SQL files, `user_version`, a pre-migration backup, one transaction per migration); verify with tests for a fresh database, an upgrade, and a failing migration that leaves the data unchanged
- [x] 2.2 Write the first migration (tables: calls, jobs with a type column, transcripts with segments and word timestamps, transcript FTS5 index, speakers with fingerprints, settings, uptime spans, service state, admin, admin sessions, admin setup code), and verify a schema test that creates an empty database and checks every table and index
- [x] 2.3 Implement typed settings with defaults and validation (store queues; poll interval 1–30 minutes, default 2; store time zone, default America/Chicago, validated against the tz database), designed so later changes can register more settings; verify tests for the defaults, rejecting out-of-range and unknown values, and a change taking effect without a restart
- [x] 2.4 Implement environment configuration (`RAVON_USERNAME`, `RAVON_PASSWORD`, `RAVON_BASE_URL`, `TRANSCRIBR_PORT`, `TRANSCRIBR_DATA_DIR`) plus log redaction, and verify a test that logs a record carrying credentials and cookies and finds none of them in the output

## 3. Ravon client and fake Ravon

- [x] 3.1 Implement the allow-list guard (spec `ravon-ingest`: read-only request allow list, date-bounded searches), and verify unit tests for every allowed and refused case plus a property-based test comparing it with a plain reference implementation
- [x] 3.2 Implement the httpx client with the guard as its transport, manual redirect checks, pacing, and backoff on consecutive failures; verify that a request bypassing the client's helpers is still refused, and that the backoff timing works with a fake clock
- [x] 3.3 Implement login, session reuse, one re-login on expiry, and stop-on-rejected-credentials with the credential-hash reset; verify against the fake Ravon for the expired-session, rejected-login and retry-login scenarios
- [x] 3.4 Implement the parsers for the queue `<select>` and the `DataTable({ data: [...] })` results (recording ID from the checkbox value), with a loud failure when the page format changes; verify with synthetic pages copying the real structure, including an empty result and a changed format
- [x] 3.5 Implement the audio download into memory with a `Content-Length` check; verify that a truncated response fails, and that a test scanning the temp and data folders after downloads finds no audio files
- [x] 3.6 Build `tests/fake_ravon/` (login, search page, search submit, recordings, controllable faults) and verify that the client test suite runs entirely against it with no network access
- [x] 3.7 Write a `realsite`-marked smoke command (`transcribr ravon-check`) that logs in, lists the queues and counts one day's calls without downloading audio, and verify it with the user against the real site (the user runs it; record the queue count and call count in the change notes)

## 4. Ingest: poller, uptime and catch-up

- [x] 4.1 Implement uptime spans from worker heartbeats (design D4), and verify tests for extending a span, starting a new span after a gap of more than 3 minutes, and the 2-minute grace
- [x] 4.2 Implement the poll cycle (design D5: per-queue windows, inserts that ignore duplicate IDs, auto-queue only when the call's end falls inside a span), and verify tests for all scenarios under "Poll for new calls" and "Automatic transcription only for calls that ended while the server was running"
- [x] 4.3 Implement the catch-up on start, the first-start 7-day listing, and "load earlier" in 7-day chunks; verify the restart-after-downtime, first-start and load-earlier scenarios against the fake Ravon
- [x] 4.4 Implement the worker main loop (heartbeat, settings reread, poll schedule, job processing, graceful shutdown), and verify an integration test that runs the worker against the fake Ravon for a simulated hour with a fake clock

## 5. Processing pipeline

- [x] 5.1 Add a script that generates the synthetic two-voice test clips (short, small, no real voices) and commit the clips; verify the tests can decode them
- [x] 5.2 Implement audio decoding to 16 kHz mono float32 in memory (PyAV, `av<19` pin), and verify a test on the fixture clips with no temporary files created
- [x] 5.3 Implement transcription with faster-whisper (`small.en`, int8, VAD, word timestamps, an optional hotword list that is empty in this change), and verify a `model`-marked test that transcribes a fixture clip, plus a unit test that a given hotword list reaches the engine
- [x] 5.4 Implement speaker separation and per-speaker fingerprints with sherpa-onnx (design D8), including splitting segments by word timestamps and the minimum-speech rules; verify a `model`-marked test that finds two speakers in the two-voice fixture and stores no audio
- [x] 5.5 Implement the job runner (claim in a transaction, states, return `processing` to `waiting` on start, 3 attempts with backoff, Ravon-outage waits that don't use attempts, manual requests ignoring duplicates); verify tests for every scenario in the `call-transcription` spec except the model-dependent ones
- [x] 5.6 Run the worker at low CPU priority (niceness 10 on Linux, below-normal class on Windows), and verify a test that a process calling it really runs at that priority; the web-latency-under-backlog check moved to 10.4, where web and worker run together

## 6. API and admin access

- [x] 6.1 Implement the FastAPI app skeleton (`/api/v1`, error format, `/api/v1/health`, serving the built UI files with an SPA fallback); verify the health endpoint and static serving in tests
- [x] 6.2 Implement the open endpoints: status (including today's listed, transcribed, Waiting and Failed counts for the home page), request transcription of a call, and load earlier calls; verify tests for each, including the duplicate-request case
- [x] 6.3 Implement admin access (design D12): the setup code on start while no admin exists, `/api/v1/auth/state`, `/api/v1/auth/setup`, login and logout, password change under `/api/v1/admin/`, Argon2id hashing, hashed server-side sessions with 12-hour expiry, the `SameSite=Strict` cookie, the required `X-Transcribr: 1` header on every API write, and per-IP backoff; verify tests for every `admin-access` scenario
- [x] 6.4 Implement the admin settings endpoints under `/api/v1/admin/` (read and change settings, the queue list from the worker's cache plus a refresh request, retry login), and have the worker refresh the cached queue list at start, every 6 hours and on request; verify tests for the `instance-settings` scenarios, including "Password never exposed"
- [x] 6.5 Add `transcribr reset-admin`, and verify a test that it removes the admin and sessions and prints a new working setup code
- [x] 6.6 Add a test that walks the generated route list and asserts every `/api/v1/admin/` route rejects requests without a valid admin session, while every open route works without one
- [x] 6.7 Add a test that calls every GET endpoint and asserts the database is unchanged and no Ravon request was made, plus a test that the generated OpenAPI document covers every route

## 7. Web app shell and admin screens

- [x] 7.1 Build the app shell (app bar; admin links only for a logged-in admin; a footer with a small "Admin" link to `/admin`; the service status banner; the 10-second refetch), and verify Vitest tests that the banner renders for each status kind and that admin links are hidden without a session
- [x] 7.2 Complete the light and dark colour schemes (design D9, token tables in `docs/architecture.md`), add `InitColorSchemeScript` and the Light / Dark / System menu saved under Transcribr's own storage keys; verify a unit test that computes the contrast of every text/background token pair in both schemes and fails below 4.5:1, plus component tests that the menu choice persists across a remount and that another app's saved mode is ignored
- [x] 7.3 Build the home page with the collection status (last check, today's listed and transcribed counts, Waiting and Failed) and the first-setup notice when no queue is chosen; verify component tests for the working and not-set-up states
- [x] 7.4 Build the admin login, first-time setup (setup code, then username and password with the 12-character rule), log out, and change password screens; route any `/admin` page to login or setup when there is no session; verify component tests for each flow, including a wrong setup code and a short password
- [x] 7.5 Build the Settings view at `/admin/settings` (the queue picker read from Ravon, poll interval, time zone, validation messages, the Ravon login panel with Retry login, the admin account section), structured so later changes can add sections; verify component tests including rejected values

## 8. Status and operations

- [x] 8.1 Implement the status report (worker heartbeat age, last successful poll, Ravon state, queue length, failures in the last 24 hours, allow-list violations), and verify tests for the healthy, worker-stopped, login-failed, no-credentials and unreachable states
- [x] 8.2 Implement `transcribr worker-health` and `transcribr backup` (the SQLite backup API into `/data/backups`), and verify that the backup restores into a fresh data folder with identical counts
- [x] 8.3 Implement structured logging to stdout and a rotating file under `/data/logs`, and verify that the redaction test from 2.4 also passes through both outputs

## 9. Packaging and deployment

- [x] 9.1 Write the multi-stage Dockerfile (UI build, a model stage with pinned revisions and SHA-256 checks, a Python 3.14 slim runtime, non-root uid 10001), and verify `docker build` succeeds and `docker run --rm <image> id -u` prints 10001
- [x] 9.2 Write `compose.yaml` (`web` and `worker` from one image, a named volume, `restart: unless-stopped`, health checks, the worker waiting for a healthy web, only the web port published) and `.env.example`; verify `docker compose up -d` gives two healthy services
- [x] 9.3 Verify the no-runtime-downloads requirement by running the stack with outbound network restricted to the fake Ravon and processing a fixture call end to end
- [x] 9.4 ~~Build and run the arm64 image and verify the fixture pipeline test inside it~~ Narrowed on 2026-10-23: the instance runs on amd64 only (64-bit Intel/AMD; no arm hardware to test on). Done instead: the arm64 image builds under emulation, its native libraries load and the 292 non-model tests pass; the model test was stopped after an hour under emulation
- [x] 9.5 Write the README (install on Linux, Windows with Docker Desktop and auto-start, and macOS; `.env`; first setup, including finding the admin setup code in `docker compose logs web` and `reset-admin`; updating; backup and restore; troubleshooting the banner states and a page that ignores the Windows light/dark setting: Firefox Settings → General → Website appearance → Automatic, Chrome/Edge appearance set to follow the device), and verify by following it on a clean host to a working instance (Done on 2026-10-23 on the dev laptop rather than a clean host: the user reviewed the README, and its build, start, setup-code, queue, auto-transcription and backup/restore steps were run against the fake Ravon on the offline test stack. The first run with real Ravon credentials on the shop PC happens in 10.3.)

## 10. End-to-end checks

- [x] 10.1 Run a compose smoke test of web + worker + fake Ravon: the admin is created from the logged setup code and chooses a queue; a new call is listed and auto-transcribed; a call during simulated downtime stays Not transcribed until its transcribe action is sent; the home page counts match; verify that it passes in the `check` script (Passed 2026-10-23: `scripts/stack_check.py smoke`, the last step of `check.py`; `--quick` skips it.)
- [x] 10.2 Run the resilience checks: kill the worker mid-call, restart Docker, recreate the containers, and update to a rebuilt image with a no-op migration; verify that no call is lost, duplicated or stuck, and that data persists (Passed 2026-10-23: `stack_check.py resilience` covered the worker kill mid-call, container recreation and a no-op-migration update; the user restarted Docker Desktop and `stack_check.py verify` matched the saved snapshot.)
- [ ] 10.3 With the user, run the instance against the real Ravon for one working day on the shop PC, then compare its listed-call count with Ravon's search for the same day and check how many were transcribed, and record the results in the change notes
- [x] 10.4 With the compose stack and a backlog of 50 fixture calls processing, verify that the home page and status API answer within 2 seconds (the `call-transcription` "Background processing without starving the server" scenario, moved from 5.6) (Passed 2026-10-23: `stack_check.py backlog`; while the queue went from 50 to 45, 176 requests each to the home page and status API had a median of 5 ms, slowest 23 ms and 27 ms.)

## Workflow follow-up

- Run `/opsx:verify` and review the real-day results before archiving.
- Archive this change with `/opsx:archive` once all tasks are done, so its specs become the main specs.
- Then continue with `add-call-browser`, then `add-call-attribution`, then `add-mcp-server`.
