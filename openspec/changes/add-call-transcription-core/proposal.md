# Proposal

## Why

A service writer at the shop often promises customers he'll look into something, like a lift kit for their truck or rims that fit their vehicle. Afterwards he has to dig through Ravon's recordings and re-listen to calls to remember the details. Ravon can't tell which calls are his, because inbound calls land on the main store line. Finding a call means scrolling through every store call by time and playing them one by one.

This change builds the core of Transcribr v2. It is a small server on a shop PC that collects the store's call recordings and transcribes them. It works out which calls belong to which service writer and lets him copy a transcript, with a research prompt, into his own ChatGPT.

## What Changes

- **Collect calls from Ravon (read-only):** log in, poll the recordings search on a schedule, and list every call for the configured store queues. Fetch recording audio into memory only. Only an allow list of read-only requests can reach Ravon.
- **Transcribe new calls automatically:** a call is transcribed automatically if it ended while the server was running. Calls that ended while the server was off are listed as "Not transcribed" and only transcribed when someone clicks Transcribe. The server never backfills on its own.
- **Find the speakers in each call:** separate the speakers in the mono recording, label each transcript segment with its speaker, and keep a voice fingerprint per speaker (never the audio).
- **Attribute calls to people:** match each transcribed call to configured profiles using names said in the call and voice similarity. Record the person, method and confidence per call, with "Maybe" for uncertain matches. Users can correct attributions by hand.
- **Profiles set up in the app:** add a person, their name variants, and a voice profile built from calls they pick ("this is me"). Nothing person-specific lives in code.
- **Admin area at `/admin`:** People and Settings sit behind a single admin login. The admin account is created on the first visit, using a one-time setup code printed in the server log. Everyone else uses the call screens without logging in, including every call action.
- **Web app on the shop network:** one view of all calls, with filters for a person, Unassigned, Maybe, status, date and text search. Each call has a transcript view with speaker names, a Listen button that streams from Ravon through the server, a **Copy for ChatGPT** button, and Transcribe/Retry. Profile management and settings are in the admin area.
- **Instance settings in the app:** store queues, poll interval, time zone, research prompt template and matching thresholds. Ravon credentials come from the deployment's environment file.
- **Deploy as one Docker image:** run on any OS with Docker (Linux, Windows via WSL2, macOS; amd64 and arm64). Data lives in one named volume, and the image needs no internet access at runtime except to reach Ravon.
- **Out of scope (follow-up change):** a read-only MCP server so ChatGPT can query Transcribr. It sits behind a secure tunnel with OAuth and is a client of the REST API this change builds. This change only makes sure the API is suitable for it.

## Capabilities

### New Capabilities
- `ravon-ingest`: talking to Ravon read-only. Covers login and re-login, the request allow list, polling the recordings search, listing calls, the server-uptime rule that decides which calls are auto-transcribed, and fetching audio into memory.
- `call-transcription`: the processing queue and pipeline. Covers turning a call's audio into a speaker-labeled transcript with per-speaker voice fingerprints, automatic and manual jobs, retries, failure reporting and crash recovery.
- `call-attribution`: people profiles (name variants, voice enrollment) and assigning calls to people by name, by voice, or by hand, with method and confidence.
- `call-browser`: the shop-network web app and REST API for listing, filtering, searching and reading calls, listening to recordings, copying a transcript for ChatGPT, and requesting transcription.
- `admin-access`: the admin area at `/admin`. Covers first-visit admin creation with a setup code, login and sessions, protection of admin screens and API endpoints, failed-login slowdown, and password change and reset.
- `instance-settings`: per-instance configuration stored with the instance's data. Covers store queues, schedule, time zone, prompt template and thresholds, plus environment-provided secrets and service status reporting.
- `deployment`: packaging and running the instance as a container on any supported OS and CPU architecture, with persistent data, automatic restart and health checks.

### Modified Capabilities
- None (new project, no existing specs).

## Impact

- **New codebase:** a Python backend (API, worker, Ravon client) and a React + TypeScript frontend in this repository. Nothing is reused from the v1 prototype except verified facts about Ravon and the audio.
- **External system:** Ravon admin site (`admin.ravon.net`), read-only. It adds steady but light load: one date-bounded search per queue every few minutes, plus one audio download per processed call.
- **Dependencies:** a speech-to-text engine and model, a speaker separation and voice embedding toolkit with its models, SQLite, and Docker. Models are baked into the image, so a running instance needs no model downloads.
- **Data and privacy:**
  - Transcripts contain customer conversations and phone numbers.
  - Voice fingerprints of staff are biometric data. Each person should consent before a voice profile is built for them.
  - All data stays on the shop PC. Audio is never written to disk.
- **Operations:** someone at the shop keeps the PC and Docker running. Updating means pulling a new image and restarting, and data is kept across updates.
