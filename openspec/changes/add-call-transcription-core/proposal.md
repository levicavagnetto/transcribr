# Proposal

## Why

A service writer at the shop often promises customers he'll look into something, like a lift kit for their truck or rims that fit their vehicle. Afterwards he has to dig through Ravon's recordings and re-listen to calls to remember the details. Ravon can't tell which calls are his, because inbound calls land on the main store line.

Transcribr v2 fixes this in three changes. This first change builds the core that everything else depends on: a server on a shop PC that reliably collects every store call from Ravon and transcribes new ones, with an admin-protected setup, a health view, and a Docker deployment. The follow-up changes add the staff call screens (`add-call-browser`) and matching calls to people (`add-call-attribution`).

## What Changes

- **Collect calls from Ravon (read-only):** log in, poll the recordings search on a schedule, and list every call for the configured store queues. Fetch recording audio into memory only. Only an allow list of read-only requests can reach Ravon.
- **Transcribe new calls automatically:** a call is transcribed automatically if it ended while the server was running. Calls that ended while the server was off are listed as "Not transcribed" and only transcribed on request. The server never backfills on its own.
- **Find the speakers in each call:** separate the speakers in the mono recording, label each transcript segment with its speaker, and keep a voice fingerprint per speaker (never the audio). `add-call-attribution` uses these fingerprints for voice matching.
- **Admin area at `/admin`:** settings sit behind a single admin login. The admin account is created on the first visit, using a one-time setup code printed in the server log.
- **Instance settings in the admin area:** store queues, poll interval and time zone. Ravon credentials come from the deployment's environment file.
- **Web app shell on the shop network:** open without a login. It has light and dark themes that follow the device, a status banner when something needs attention, a home page showing collection status, a footer link to the admin area, and a documented REST API where every read is side-effect free.
- **Deploy as one Docker image:** run on any OS with Docker (Linux, Windows via WSL2, macOS; amd64 and arm64), with two services (`web` and `worker`) sharing one named volume. The running instance makes no network requests except to Ravon.
- **Out of scope (follow-up changes):**
  - **`add-call-browser`:** call list, search, call detail, Listen and Copy for ChatGPT.
  - **`add-call-attribution`:** people profiles, name and voice matching, the People admin screen, person filters.
  - **`add-mcp-server`:** a read-only MCP server for ChatGPT.

## Capabilities

### New Capabilities
- `ravon-ingest`: talking to Ravon read-only. Covers login and re-login, the request allow list, polling the recordings search, listing calls, the server-uptime rule that decides which calls are auto-transcribed, and fetching audio into memory.
- `call-transcription`: the processing queue and pipeline. Covers turning a call's audio into a speaker-labeled transcript with per-speaker voice fingerprints, automatic and manual jobs, retries, failure reporting and crash recovery.
- `instance-settings`: per-instance configuration stored with the instance's data. Covers store queues, poll interval and time zone, environment-provided secrets, and service status reporting.
- `admin-access`: the admin area at `/admin`. Covers first-visit admin creation with a setup code, login and sessions, protection of admin screens and API endpoints, failed-login slowdown, and password change and reset.
- `web-app`: the shop-network web app shell. Covers open access, the footer admin link, light and dark themes, the status banner, the collection-status home page, and the REST API rules.
- `deployment`: packaging and running the instance as a container on any supported OS and CPU architecture, with persistent data, automatic restart and health checks.

### Modified Capabilities
- None (new project, no existing specs).

## Impact

- **New codebase:** a Python backend (API, worker, Ravon client) and a React + TypeScript + MUI frontend in this repository. Nothing is reused from the v1 prototype except verified facts about Ravon and the audio.
- **External system:** the Ravon admin site (`admin.ravon.net`), read-only. It adds steady but light load: one date-bounded search per queue every few minutes, plus one audio download per processed call.
- **Dependencies:** a speech-to-text engine and model, a speaker separation and voice embedding toolkit with its models, SQLite, and Docker. Models are baked into the image.
- **Data and privacy:** transcripts contain customer conversations and phone numbers. Voice fingerprints of everyone on a call are stored, but no audio. All data stays on the shop PC.
- **Operations:** someone at the shop keeps the PC and Docker running. Updating means pulling a new image and restarting, and data is kept across updates.
