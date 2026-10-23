# Design

## Context

See `proposal.md` for the motivation and `specs/` for the required behavior. The block diagram lives in `docs/architecture.md` and must stay in sync with this file.

Verified facts this design relies on (measured against the real site and audio during the v1 prototype):

- **Login:** a plain form POST of `username` and `password` to `/auth/login`. There is no CSRF token. The session cookies are `JSESSIONID` and `session`. Sessions expire after about 30 minutes idle, so regular use keeps one alive for hours.
- **Searching:** a POST to `/realtime/manage_recorded_calls.html` with eight fields: `queue`, `user`, `conferencePK`, `startDate`, `endDate`, `ani`, `dnis` and `query=Find Calls`.
  - Dates use the format `YYYY-MM-DD HH:MM:SS` in the store's local time.
  - A search without dates hung for more than 20 seconds.
  - Results come in an inline script, `$("#recordingTable").DataTable({ data: [...] })`. Each row has the keys `select` (the checkbox `value` is the recording ID), `Start Time`, `Minutes`, `From`, `To` and `tools`.
  - All rows come back in one page; the site has no server-side paging.
- **Delete controls:** the same page holds them (`checked` checkboxes, and the `delete` and `deleteAll` buttons). A search must never send anything beyond the eight fields.
- **Audio:** `GET /recordings/{id}` returns an MP3 with `Content-Length`. It is MPEG 2.5 layer III, 8 kHz, 64 kbps, **mono**, about 430 KB per minute.
- **Volume:** about 70 calls per weekday on the main store queue, averaging 2.5 minutes, about 3 hours of audio per day.
- **Speed:** `faster-whisper` `small.en` int8 on a laptop CPU ran at about 0.11× real time, which comes to about 20 minutes of compute per day of calls. It needs `av<19`, because `av` 19 removed an option `faster-whisper` uses.
- **Hugging Face downloads** were very slow from the shop network (about 25 KB/s).

## Goals / Non-Goals

**Goals:**
- As few moving parts as possible, each of which survives a crash, restart, reboot or Ravon outage without losing or duplicating work.
- Clear boundaries: the Ravon client, ingest, pipeline, API and UI can each be tested alone.
- Store everything later changes need (transcripts, word timestamps, per-speaker fingerprints), so `add-call-browser` and `add-call-attribution` never have to re-download audio.

**Non-Goals:**
- The MCP server, the tunnel and OAuth. They belong to the follow-up change, `add-mcp-server`. This change only keeps the API GET-pure and documented.
- Per-person user accounts. There is one admin login for the admin area, and the rest of the web app is open to everyone on the shop network.
- The call screens (`add-call-browser`) and people profiles and matching (`add-call-attribution`). Their designs live in those changes.
- Summaries or research done by the app. ChatGPT does that.
- GPU acceleration, live (in-call) processing, and any use of Ravon's live-call page or `ajax.html` endpoints.
- More than one store per instance. Another store means another instance.

## Decisions

### D1. One image, two compose services: `web` and `worker`
Both services run from the same image with different commands.
- `web` runs FastAPI, serving the API and the built React files.
- `worker` runs the poller and the processing pipeline.

They share one named volume. The operator still runs one `docker compose up -d`.
- **Why:** transcription is CPU-heavy and native code can crash. In a separate service, a worker crash never takes the web app down, and Docker restarts each one on its own. This is what the "worker crash" scenario in `deployment` requires.
- **Alternatives:**
  - A single process with a background thread: a crash or stall would take the web app down with it.
  - A process supervisor inside one container: one more moving part, and it hides crashes from Docker.
  - Separate images: two things to build and version.

### D2. SQLite (WAL mode) on a named Docker volume as the only datastore
Calls, jobs, transcripts, fingerprints, settings, uptime and admin data all live in one SQLite file, and later changes add their tables to it through migrations. Both services open it with WAL mode and a busy timeout. Only `web` applies migrations, and `worker` waits until `web` is healthy before starting.
- **Why:** there's no database server to run, backups are a single file, and load is tiny (about 70 calls a day).
- **Named volume, never a bind mount:** on Docker Desktop for Windows and macOS, bind mounts go through a file-sharing layer where SQLite locking is unreliable. A named volume lives on the Linux VM's own file system.
- **Alternative:** Postgres, which would mean an extra service, extra upgrades and extra backup steps for no real benefit at this scale.
- **Migrations:** numbered SQL files tracked with `PRAGMA user_version`. Before a migration runs, a backup copy is made with the SQLite online backup API, and each migration runs in a transaction.

### D3. The job queue is a table
A `jobs` table holds one row per pending job. A job has a type; this change has only `transcribe` (a call ID). The type column lets later changes add job types (for example a rematch) without a schema rewrite.
- The single worker claims the oldest job in a transaction.
- On start, the worker returns every `processing` call to `waiting`.
- Retries track an attempt count, with a backoff of 1, 5 and then 30 minutes.
- When the error is about Ravon being unavailable (login failed, unreachable), the job waits and doesn't spend an attempt.
- **Alternative:** Redis or Celery: another service, and more than one worker isn't needed.

### D4. "Server was running" comes from worker heartbeats, recorded as uptime spans
- Every 30 seconds the worker writes a heartbeat. If the last span ended within the last 3 minutes, the heartbeat extends it; otherwise it starts a new span.
- A newly listed call is queued automatically only if its end time (`Start Time` + `Minutes`) falls inside a span. A 2-minute grace on each side covers clock jitter.
- On the very first start, nothing earlier than the first span qualifies.
- **Each queue also has a "followed since" time,** recorded when the worker first sees it selected (and cleared if it's deselected). A call is auto-queued only if it ended inside a span **and** after its queue was followed. This covers the spec's "add a queue later" rule: a new queue's older calls are listed but never queued, even if the server was running when they ended.
- A Ravon outage doesn't break the span, because the worker keeps running, so calls that ended during it still qualify.
- **Why:** it's simple and durable, and it captures exactly what the user asked for. It doesn't depend on whether a poll succeeded.
- **Alternative:** "last successful poll" times. They would wrongly treat Ravon outages as server downtime.

### D5. Polling windows
- Each poll searches each selected queue from 2 hours before the last successful poll up to now. The overlap catches long calls, which only appear once they've ended.
- On start, the worker catches up from 1 day before the newest known call up to now, in chunks of 7 days or less.
- On the first start, it lists the last 7 days.
- "Load earlier" lists the 7 days before the earliest time already listed. That boundary is stored (`listed_from`), set by the first-start listing and moved back by each "load earlier". It's not taken from the oldest call, which can sit well inside the listed range on quiet days.
- The recording ID is the key, and inserts that would duplicate it are ignored.
- The default poll interval is 2 minutes.
- **Times:** Ravon's `Start Time` is in the store time zone setting. It's stored as-is (`start_local`) and converted to UTC (`start_utc`) on insert. Search windows are computed in UTC and converted to store-local wall time for the search form.
- **"Load earlier"** runs in the worker, which owns the Ravon session: the API queues a `load_earlier` job, and the worker carries it out on its next loop.
- Requests go out one at a time, at least 1 second apart. After 5 failures in a row, the worker backs off with increasing delays, up to a 10-minute cap.

### D6. The Ravon client enforces the allow list at the transport layer
- The client is `httpx`, with a custom transport that checks every outgoing request against the allow list. Redirects are disabled and handled by hand, so each hop is checked too.
- Building a request any other way doesn't bypass the check, because the transport is the only way out.
- The allowed requests are:
  - `GET /auth/login` and `POST /auth/login` with exactly `username` and `password`
  - `GET /realtime/manage_recorded_calls.html`, used to read the queue `<select>`
  - `POST` to the same page with exactly the eight search fields, valid dates and a span of 7 days or less
  - `GET /recordings/{id}` for IDs already stored from search results
- Anything else is refused before it's sent. Refusals are counted and logged with the method and path only.
- **Results parsing:** the client finds the `DataTable({ data: ... })` array, decodes it as JSON, and takes the ID from the checkbox `value`. If that structure is missing, the poll fails with a clear "Ravon page format changed" status, instead of returning zero calls without saying so.
- `web` has its own client instance, limited to login and recording GET, for Listen. Each service keeps its own session, which Ravon allows. The login-failed state is shared through the database.

### D7. Transcription: faster-whisper `small.en`, int8, CPU
- **Settings:** VAD filter on, word timestamps on. The transcriber takes an optional list of hotwords, passed to faster-whisper's `hotwords` option. It is empty in this change; `add-call-attribution` fills it with people's name variants.
- **Decoding:** audio bytes go through PyAV into 16 kHz mono float32 in memory and are never written to a file.
- **Priority:** the worker runs at a low priority (niceness 10), so `web` stays responsive.
- **Model choice:** the model name is a build argument, defaulting to `small.en`. A bigger model is a rebuild, not a code change.
- **Alternatives:**
  - `openai-whisper`: PyTorch-based, slower on CPU.
  - Cloud speech APIs: audio would leave the shop, and they cost money.

### D8. Speakers and fingerprints: sherpa-onnx
- **Speaker separation:** sherpa-onnx's offline speaker diarization runs a pyannote segmentation model (pyannote segmentation 3.0) and a speaker-embedding model (WeSpeaker ResNet34, English), both ONNX. The number of speakers is found by a clustering threshold, provisionally 0.35. On the synthetic clip, 0.3-0.4 separates two voices and a larger value gives fewer speakers; see `notes.md`.
- **Matching segments to speakers:**
  - Each whisper segment goes to the speaker it overlaps most.
  - A segment that spans a speaker change is split at word boundaries using the word timestamps.
- **Fingerprints:**
  - A speaker's fingerprint is the L2-normalized mean of the embeddings of their speech, computed from turns of 1.5 seconds or longer.
  - It is stored as a float32 blob along with the speech seconds it came from.
  - A speaker with less than 3 seconds of usable speech gets no fingerprint.
- **Why:** it runs on CPU without PyTorch, its models are small (tens of MB), and it has wheels for Linux amd64 and arm64.
- **Alternatives:**
  - pyannote.audio, SpeechBrain and WhisperX: all of them pull in PyTorch. The image would be several GB, and pyannote's gated models need a Hugging Face token.
- **Telephone audio:** these models are trained on 16 kHz audio and ours is upsampled 8 kHz. How well fingerprints separate people is measured on real calls in `add-call-attribution`, before its thresholds are fixed.

### D9. API and UI
- **API:** FastAPI under `/api/v1`, with Pydantic models and an auto-generated OpenAPI description.
  - Reads are GET-only and have no side effects.
  - Lists use cursor paging on (`start_time`, `id`).
  - `GET /api/v1/health` is the health check for `web`.
- **UI:** React + TypeScript, built with Vite.
  - TanStack Query refetches every 10 seconds, which covers the 30-second "Live updates" requirement without WebSockets or server-sent events.
  - React Router handles the views: the home page, `/admin/login`, `/admin/setup` and `/admin/settings`. Later changes add their own views.
  - Components come from **MUI** (`@mui/material`, Material Icons), chosen by the user. One custom theme (`frontend/src/theme.ts`) holds the palette, type, shape and component overrides, so screens use theme values and never one-off colors. The mockups are linked from `docs/architecture.md`.
  - **Themes:** one `createTheme` call with `cssVariables: true` and `colorSchemes: { light, dark }`, both built only from the Ubuntu/Canonical palette and its published tints. The token tables are in `docs/architecture.md`. MUI's `InitColorSchemeScript` in `index.html` applies the saved or system scheme before React loads, so there's no flash. `useColorScheme()` drives a Light / Dark / System menu in the app bar, saved in browser storage under Transcribr's own keys (`transcribr-mode`, `transcribr-color-scheme`), because MUI's default `mui-mode` key is shared by every app on the same origin and a stale value there overrides the device setting. In dark mode MUI's AppBar ignores its colour and paints `palette.AppBar.darkBg`, so the dark scheme sets that to dark aubergine. Every component uses theme tokens, never literal colours, so both themes come from one set of components.
  - **Dark theme approach:** neutral grey grounds (text grey `#111111`, cool grey `#333333`) instead of large aubergine fields, with the dark aubergine kept for the app bar. Full-strength aubergine and orange are too dark or too low-contrast as text on dark grounds, so light tints from the palette take those roles: light aubergine 40% for primary, orange 60% for orange text and icons. Full Ubuntu orange stays for filled accents with dark labels.
  - Alternative: plain CSS with no component library. It's smaller, but every table, form field, dialog and snackbar would have to be built and made accessible by hand.

### D10. Configuration split
- **Environment file** (`.env` next to the compose file):
  - `RAVON_USERNAME` and `RAVON_PASSWORD`
  - optionally `RAVON_BASE_URL`, defaulting to `https://admin.ravon.net`
  - `TRANSCRIBR_PORT`
- **Database settings table:** everything else (queues, poll interval, time zone, and the settings later changes add), edited in the admin Settings screen and validated with Pydantic.
- The worker rereads settings every loop, so changes apply without a restart.
- **Why:** this keeps the password out of the database, the API and backups. Only the admin can change settings, and nobody, not even the admin, can read the Ravon password through the app.
- **Login-failure lockout safety:** after a rejected login, the worker stops trying.
  - It tries again when the process restarts with different credentials (a hash of the credentials is compared).
  - It also tries again when someone clicks "Retry login" in the status banner.

### D11. Image build and runtime
- **Build stages:**
  1. `node:22-slim` builds the UI.
  2. A model stage downloads the `small.en` CTranslate2 files and the two sherpa-onnx models, at pinned revisions, and checks each file against a SHA-256.
  3. `python:3.14-slim` installs the backend with `uv sync --frozen` and copies in the UI files and models.
- **Python version:** 3.14, the newest release with Linux wheels for every native dependency (ctranslate2, sherpa-onnx, onnxruntime, PyAV 18) on both amd64 and arm64, checked on PyPI on 2026-10-22. Python 3.15 (released 2026-10-09) has no ctranslate2, sherpa-onnx or onnxruntime wheels yet, so moving to it later is a version bump once they ship. v1 also ran faster-whisper on 3.14 on the dev PC.
- **Multi-arch:** images are built for amd64 and arm64 with `docker buildx`.
- **Runtime:**
  - The container runs as a non-root user (uid 10001), and `/data` is the named volume.
  - Compose sets `restart: unless-stopped` and a health check for each service.
  - The worker's health check is `transcribr worker-health`, which checks the heartbeat is less than 90 seconds old.
- **Logs:** JSON lines to stdout (`docker compose logs`) and a rotating file under `/data/logs`. Credentials, cookies and form values are redacted.
- **Backup:** `docker compose exec web transcribr backup` writes a consistent `/data/backups/transcribr-<timestamp>.db` using the SQLite backup API. The README documents copying it out and restoring it.

### D12. Admin access
- **Routes:**
  - The UI puts admin screens under `/admin/...`: `/admin/settings`, `/admin/login` and `/admin/setup`. `add-call-attribution` adds `/admin/people`.
  - The API puts every admin endpoint under `/api/v1/admin/...`.
  - A FastAPI dependency on that router enforces the admin session for every route. Hiding links in the UI is only for convenience.
- **First visit:**
  - While no admin row exists, `web` generates a 10-character setup code on start and writes it to the log in a clearly marked line. Only its hash is stored.
  - `/admin/setup` takes the code, then a username and password. Creation happens in one transaction that also deletes the code, so it can't be reused.
- **Storage:** one `admin` row (username, Argon2id hash via `argon2-cffi`, password-changed time) and a `sessions` table (random 256-bit ID stored hashed, created and expiry times).
- **The session cookie:** `HttpOnly`, `SameSite=Strict`, path `/`, 12-hour absolute expiry. `Secure` is set automatically when the request came over HTTPS.
- **Cross-site protection:** `SameSite=Strict`, plus every admin write must carry an `X-Transcribr-Admin: 1` header, which another site's form or image can't send. Writes without it are rejected.
- **Rate limiting:** an in-memory per-IP counter in `web`, with exponential backoff after 5 failures a minute, covers login and setup-code attempts. Failures are logged with the IP and username only. A restart clearing the counter is acceptable.
- **Password change and reset:**
  - Changing the password needs the current password, and ends every other session.
  - `docker compose exec web transcribr reset-admin` deletes the admin row and all sessions, then prints a new setup code.
- **Alternatives:**
  - Admin credentials in `.env`. Simpler, but the user chose creation in the app.
  - HTTP Basic auth. The browser caches it with no real logout, and it offers no protection against other sites.
  - A full user system. Not needed while there's one admin.

### D13. Code layout
```
backend/transcribr/
  ravon/        client.py (allow-list transport), parse.py, guard.py
  ingest/       poller.py, uptime.py
  pipeline/     audio.py, transcribe.py, diarize.py, process.py
  attribution/  (empty package; filled by add-call-attribution)
  store/        db.py, migrations/*.sql, repositories per table
  api/          app.py, routes/*.py, schemas.py
  settings.py, status.py, cli.py (web | worker | worker-health | backup)
frontend/       Vite React app
tests/          backend tests; fake_ravon/ (a small app that mimics the real pages)
docker/         Dockerfile, compose.yaml, .env.example
```
Each package depends only on `store` and its own inputs, so each can be tested alone with fakes.

### D14. Testing approach
- **Ravon client:**
  - Unit tests for the allow list, covering every allowed and refused case, plus a property-based test of the guard.
  - Parser tests against synthetic pages that copy the real structure, with no real customer data.
- **Fake Ravon:** a small FastAPI app with the login, search and recording endpoints and controllable faults (expired session, rejected login, 5xx errors, a changed page format, truncated audio).
- **Pipeline:**
  - Tests with short synthetic two-voice audio clips, generated by a checked-in script and kept under a few hundred KB.
  - A `model`-marked test runs the real models.
- **API:** tests against a temporary database.
- **UI:** Vitest with React Testing Library on the shell, the banner, the theme menu, and the admin login, setup and Settings screens.
- **End-to-end:** one compose-based smoke test of web + worker + fake Ravon. Listing, auto-transcription, the missed-call rule and the admin setup are covered end to end.

## Risks / Trade-offs

- **Speaker separation can merge the two speakers on short calls, or split one speaker in two.** → Fingerprints need at least 3 seconds of speech, and every speaker label keeps its own fingerprint, so later matching doesn't depend on getting exactly two speakers.
- **Ravon page changes would break parsing.** → The parser fails loudly with a status banner instead of returning zero rows. Its tests use structure copied from the real page.
- **Two processes write to SQLite.** → WAL mode, a busy timeout, short transactions, and the worker doing almost all writes.
- **Docker Desktop on Windows has to start at boot and keep WSL2 running.** → The README covers enabling "Start Docker Desktop when you sign in" and auto-login on a dedicated PC. A Linux host is the recommended setup.
- **Voice fingerprints of every speaker, customers included, are stored.** → They are needed to match staff voices later without re-downloading audio. They stay in the instance's volume, are never returned by the API, and can't be turned back into audio. Consent and enrollment rules come with `add-call-attribution`.
- **The admin password crosses the shop network unencrypted, because the app is served over plain HTTP.** → Accepted for a trusted shop network. Sessions are short (12 hours), failed logins are slowed down, and the app can later be put behind HTTPS (for example, the same tunnel as the MCP change) without code changes.
- **The setup code is printed in the server log.** → Only someone who can read the container logs can create the admin. The code is single-use and stops working once the admin exists.
- **Model downloads are slow on the shop network.** → Models are baked in at build time, so a slow network only affects building the image, and the image can be built anywhere.
- **The image will be about 1 GB with models.** → Accepted. It's pulled once per update.

## Migration Plan

This is a new system, so there's no data to migrate.

**Deployment:**
1. Build or pull the image.
2. Copy `compose.yaml` and `.env.example` to the host, and fill in `.env`.
3. Run `docker compose up -d`.
4. Open the web app, follow the footer Admin link, create the admin with the setup code from `docker compose logs web`, and choose the store queues.

**Rollback:**
1. Run `docker compose down`.
2. Start the previous image tag.
3. If a migration ran, restore the automatic pre-migration backup from `/data/backups`.

## Open Questions

- **Where are images built and published?** Options are a local build on the shop PC, GitHub Container Registry, or another registry. This doesn't affect the specs or tasks: the image and compose file are the same either way.
- **Is `small.en` accurate enough for part numbers and vehicle details across many calls,** or should the build default become `medium.en`? This is a build-argument change after real use.
