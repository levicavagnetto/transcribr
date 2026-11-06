## Why

The service writers want an LLM to look through and work with call data. The old plan was a hosted MCP server for ChatGPT, which needed a tunnel and OAuth. That is more moving parts than the shop needs. A command-line tool does the same job with nothing hosted: any AI that can run commands (Claude Code, Codex and the like) can use it, and so can a person or a script.

## What Changes

- Add data subcommands to the existing `transcribr` command, run in the web container with `docker compose exec web transcribr ...`:
  - `calls list`, filtered by day range, person, Maybe, state, unassigned and caller number.
  - `calls search "<words>"` for calls whose transcript contains the words.
  - `calls show <id>`, which prints the call's details and timestamped transcript.
  - `calls transcribe <id>`, which queues a Not transcribed or Failed call.
  - `people list` and `people add`.
  - `people claim`, `people confirm` and `people reject` for a call.
- Every command prints readable text by default and JSON with `--json`. Each one has `--help` text with examples that an LLM can learn from.
- Errors go to stderr with a non-zero exit code. Examples are "no such call" and "no such person".
- Drop the planned `add-mcp-server` change. Update the "ChatGPT -> MCP server" wording in `openspec/config.yaml` and `docs/architecture.md` to describe the CLI.

## Capabilities

### New Capabilities
- `data-cli`: command-line access to calls, transcripts and people, for people, scripts and LLMs on the shop PC.

### Modified Capabilities
None. The CLI follows the same rules as the web app: the transcription rule, and claim, confirm and reject.

## Impact

- `backend/transcribr/cli.py` gets the new subcommands. A new module holds the commands and their text and JSON output, and reuses `store/browse.py`, `store/calls.py` and `attribution/profiles.py`.
- There is no new dependency, endpoint, service or migration.
- The README gets a short "Command line" section.
- The stack smoke test gains a CLI step.
