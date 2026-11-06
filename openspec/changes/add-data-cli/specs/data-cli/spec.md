## Purpose

Lets people, scripts and LLMs on the shop PC read and work with calls, transcripts and people from the command line, without a browser or a hosted server.

## ADDED Requirements

### Requirement: Data commands run in the web container
The `transcribr` command SHALL offer `calls` and `people` subcommands. These work on the instance's database when run with `docker compose exec web transcribr ...`, need no login, and never contact Ravon. `transcribr calls --help` and `transcribr people --help` SHALL list each subcommand with a one-line description, and each subcommand's `--help` SHALL include an example.

#### Scenario: Help lists the data commands
- **WHEN** a user runs `transcribr calls --help`
- **THEN** the output names `list`, `search`, `show` and `transcribe`, each with a description

#### Scenario: No database
- **WHEN** a data command runs where there is no database
- **THEN** it prints an error to stderr and exits with a non-zero code

### Requirement: Text or JSON output
Every data command SHALL print readable text by default. With `--json`, it SHALL print exactly one JSON document to stdout and nothing else. Errors SHALL go to stderr with a non-zero exit code. With `--json`, an error SHALL also be printed as a JSON object with `error` and `message` fields.

#### Scenario: JSON output parses
- **WHEN** a user runs `transcribr calls list --json`
- **THEN** stdout is one valid JSON document holding a list of calls

#### Scenario: Unknown call
- **WHEN** a user runs `transcribr calls show 999999` and no such call exists
- **THEN** the command exits non-zero and says no such call is listed

### Requirement: List calls
`transcribr calls list` SHALL list calls newest first. Each call SHALL show its id, its start time in the store's time zone, direction, caller number, duration, state and attributed people. It SHALL accept the web call list's filters: `--from` and `--to` days, `--person`, `--maybe`, `--unassigned`, `--state` and `--number`. It SHALL show 50 calls by default, and `--limit` SHALL change that number.

#### Scenario: Filter by person
- **WHEN** a user runs `transcribr calls list --person Nolan`
- **THEN** only calls attributed to Nolan, Confident or Maybe, are listed

#### Scenario: Only Maybe calls
- **WHEN** a user runs `transcribr calls list --person Nolan --maybe`
- **THEN** only calls with a Maybe attribution to Nolan are listed

### Requirement: Search transcripts
`transcribr calls search "<words>"` SHALL list the calls whose transcript contains the words, newest first. Each result SHALL show the time and text of its first matching line. It SHALL accept the same filters as `calls list`.

#### Scenario: Phrase found
- **WHEN** a user searches for a phrase said in one call
- **THEN** that call is listed with the time and text of its first matching line

### Requirement: Show a call
`transcribr calls show <id>` SHALL print the call's details, followed by its transcript with one `[m:ss] text` line per segment. The details are the time, direction, caller number, duration, state, and each person's status and method. A call with no transcript SHALL say so in place of the transcript.

#### Scenario: Transcribed call
- **WHEN** a user runs `transcribr calls show <id>` for a transcribed call
- **THEN** the details are printed, followed by each line as `[m:ss] text`

### Requirement: Request transcription
`transcribr calls transcribe <id>` SHALL queue a Not transcribed or Failed call for the worker, following the same rule as the Transcribe button. A call in any other state SHALL be left alone. In both cases the command SHALL report the call's state.

#### Scenario: Not transcribed call
- **WHEN** a user runs `transcribr calls transcribe <id>` for a Not transcribed call
- **THEN** the call is queued and the command reports it as Queued

#### Scenario: Already transcribed
- **WHEN** the call is already transcribed
- **THEN** nothing changes and the command reports Transcribed

### Requirement: People commands
`transcribr people list` SHALL list each person with their id, name, name variants and call counts. `transcribr people add "<name>" --variant <spelling>` SHALL create a person, including the rematch, the same way the People screen does. Any command that takes a person SHALL accept either an id or a case-insensitive name, and SHALL fail with a clear error when the name matches nobody.

#### Scenario: Add a person
- **WHEN** a user runs `transcribr people add "Nolan" --variant Nolan --variant Nolen`
- **THEN** the person is created and a rematch is queued, as when they are added on the People screen

#### Scenario: Unknown person name
- **WHEN** a command is given `--person Bob` and nobody is named Bob
- **THEN** it exits non-zero and says no person is named Bob

### Requirement: Claim, confirm and reject from the command line
`transcribr people claim|confirm|reject <person> <call-id>` SHALL make the same change as the matching call-screen action. Claim and confirm make the call Confident for the person, set by hand. Reject marks the call as not theirs, and the call stays that way. After each change, the command SHALL print the call's people.

#### Scenario: Confirm a Maybe
- **WHEN** a user runs `transcribr people confirm Nolan <id>` for a call where Nolan is Maybe
- **THEN** Nolan is Confident on that call, with method manual

#### Scenario: Reject sticks
- **WHEN** a user runs `transcribr people reject Nolan <id>` and a rematch runs later
- **THEN** Nolan is not added back to that call
