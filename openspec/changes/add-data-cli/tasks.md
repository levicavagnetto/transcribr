## 1. Command skeleton and output

- [x] 1.1 Add `transcribr/data_cli.py` with the `calls` and `people` subparsers, each with help text and an example, and wire them into `cli.py`. Verify that a test checks `transcribr calls --help` and `transcribr people --help` name every subcommand.
- [x] 1.2 Add the shared `--json` flag, the error output (D6), the no-database error and person lookup by id or name (D3). Verify with tests for an unknown call, an unknown name, a name shared by two people, and a missing database.

## 2. Calls commands

- [x] 2.1 Implement `calls list` with `--from`, `--to`, `--person`, `--maybe`, `--unassigned`, `--state`, `--number` and `--limit` over `browse.list_calls`. Verify with tests for each filter, in both text and `--json`.
- [x] 2.2 Implement `calls search` with the same filters. Verify with a test that it finds a phrase and prints the matching line's time and text.
- [x] 2.3 Implement `calls show`, which prints the details and then `[m:ss] text` lines. Verify with tests for a transcribed call and an untranscribed call.
- [x] 2.4 Implement `calls transcribe` over `request_transcription`. Verify with tests for a Not transcribed call (Queued) and a Transcribed call (left alone).

## 3. People commands

- [ ] 3.1 Implement `people list` and `people add` (with `--variant`). Verify with tests that a rematch is queued on add and that duplicate or invalid names give the same errors as the People screen.
- [ ] 3.2 Implement `people claim`, `people confirm` and `people reject` over `Attributions`. Verify with tests that confirm makes a call Confident with method manual, and that a rejected call stays rejected after `rematch_all`.

## 4. Docs and stack check

- [ ] 4.1 Add a "Command line" section to the README. Replace the MCP wording in `openspec/config.yaml` (constraint and build order) and in `docs/architecture.md` with the CLI. Verify that the README examples run as written against the stack.
- [ ] 4.2 Add a step to `scripts/stack_check.py` that runs `docker compose exec web transcribr calls list --json` and `calls show` on a smoke-test call and checks the JSON. Verify that the full `scripts/check.py` passes.

## Workflow follow-up

- Run opsx:verify, then archive the change.
