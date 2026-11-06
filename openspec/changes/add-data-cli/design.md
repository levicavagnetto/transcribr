## Context

The `transcribr` CLI (`backend/transcribr/cli.py`, argparse) already has app-running commands such as `web`, `worker` and `backup`. These open the database with `store.db.connect` and do the work inside the container. The data logic the CLI needs already exists, and the API routes use it:

- **Listing and search:** `store/browse.py` (`list_calls` with `CallFilter`, `call_detail`, `transcript`, `attributions`, `people_counts`)
- **Transcription requests:** `store/calls.py` (`request_transcription`)
- **People and attributions:** `attribution/profiles.py` (`Profiles`, `Attributions`, `ProfileError`). `Profiles.create` already queues the rematch.

## Goals / Non-Goals

**Goals:**
- Calls and people commands that are thin wrappers over those functions, so the CLI and web app can't disagree.
- Stable `--json` output an LLM can parse.

**Non-Goals:**
- An MCP server, a hosted service or a remote client.
- Running the CLI outside the container against the REST API.
- Editing or deleting people, changing settings, admin functions, and audio.

## Decisions

- **D1: Open the database directly, not through the REST API.** The CLI runs in the same container as the web app and can use the same code. There is no cookie, setup or port to manage. SQLite in WAL mode handles a short write alongside the web and worker services, as it already does for `backup`. The alternative was an HTTP client against `localhost:8000`, which would need admin login for `people add` and more code for no gain.
- **D2: Keep the code in one new module, `transcribr/data_cli.py`.** It registers its subparsers into `build_parser()` and handles the commands. Formatting stays out of `store/`: text output is built in the module, and JSON uses the same dict shapes `browse` returns. `cli.py` only wires it in.
- **D3: People may be named by id or name.** A number is read as an id. Anything else is matched against display names, ignoring case. If two people share a name, the command fails and lists their ids. This lets an LLM write `--person Nolan` without looking up an id first.
- **D4: Show times in the store's time zone.** Times use the zone from settings, as on the call list. JSON also carries the UTC start time, so scripts can sort and compare times reliably.
- **D5: Pagination is `--limit` only.** The default is 50. `--limit 0` means all calls. The web app's cursor isn't needed for a one-shot command.
- **D6: Exit codes.** 0 means OK, 1 means a not-found or invalid-input error, and argparse's own exit 2 means usage errors. With `--json`, an error prints `{"error": code, "message": text}` to stdout, and a message also goes to stderr. This lets callers parse it either way.
- **D7: Docs.** The README gets a "Command line" section with the `docker compose exec web transcribr ...` form and examples. The config and architecture doc swap the MCP line for "LLM -> transcribr CLI (in the web container) -> transcribr DB". The CLI never touches Ravon or credentials.

## Risks / Trade-offs

- [An LLM with shell access can change attributions.] → These are the same no-login actions anyone on the shop network already has. People can't be deleted from the CLI.
- [`docker compose exec` must run from the folder that holds the compose file.] → The README shows the command and the folder to run it from.
- [Write contention with the worker.] → Each write is one short transaction, and the existing busy timeout covers it.
