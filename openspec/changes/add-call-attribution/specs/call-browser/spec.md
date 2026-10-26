# Spec Delta

## ADDED Requirements

### Requirement: Person filters on the call list
The call list SHALL filter by person, Maybe and Unassigned, combined with the state, date and search filters. Each row SHALL show its attributed people, with Maybe attributions marked differently from Confident ones.

#### Scenario: Filter to one person
- **WHEN** a user selects the Nolan filter
- **THEN** only calls attributed to Nolan (Confident or Maybe) are shown, with Maybe calls marked

#### Scenario: Review uncertain calls
- **WHEN** a user selects the Maybe filter
- **THEN** only calls with at least one Maybe attribution are shown

#### Scenario: Search within a person's calls
- **WHEN** a user filters to Nolan and searches "lift kit"
- **THEN** only Nolan's calls whose transcript contains "lift kit" are shown

### Requirement: Attribution on the call screen
A call's screen SHALL show each attributed person with confidence, method, the name heard and its time, and the voice presence score. Anyone on the shop network SHALL be able to claim the call for a person, reject a person, and confirm a Maybe, without logging in. The logged-in admin SHALL also be able to tick transcript lines and enroll them for a person.

#### Scenario: Why a call is Nolan's
- **WHEN** a user opens a call attributed to Nolan by name and voice
- **THEN** the screen shows the name heard with its time and Nolan's voice presence score

#### Scenario: Call actions without login
- **WHEN** a staff member who is not logged in as admin opens a call
- **THEN** they can claim, reject or confirm attributions, and they see no enrollment tick boxes

#### Scenario: Admin enrolls from the call screen
- **WHEN** the logged-in admin opens a transcribed call
- **THEN** each line with a voiceprint has a tick box, and "Enroll as <person>" adds the ticked lines to that person's voice profile

### Requirement: Person filter in the call API
The call list API SHALL accept a person, Maybe or Unassigned filter, and SHALL return each call's attributions, so clients such as a future MCP server can list one person's calls.

#### Scenario: List a person's calls since a time
- **WHEN** a client lists Nolan's calls since a given time
- **THEN** it receives those calls with their attributions, in pages, with a cursor for the next page

## MODIFIED Requirements

### Requirement: Call detail
Opening a call SHALL show its start time, length, caller number, answered-by text, queue and processing state, how and when it was transcribed (automatically or on request), plus the transcript as timestamped lines. Lines SHALL NOT be labeled by speaker or person. It SHALL show the actions that fit the call's state.

#### Scenario: Transcribed call
- **WHEN** a user opens a Transcribed call
- **THEN** the transcript is shown as timestamped lines without speaker labels, along with Copy for ChatGPT and Listen

#### Scenario: Not transcribed call
- **WHEN** a user opens a call that is Not transcribed
- **THEN** a Transcribe button is shown, and clicking it makes the call Waiting

#### Scenario: Failed call
- **WHEN** a user opens a Failed call
- **THEN** the failure reason and a Retry button are shown

#### Scenario: Call with no speech
- **WHEN** a user opens a Transcribed call marked "no speech"
- **THEN** the page says the recording had no recognizable speech

### Requirement: Copy for ChatGPT
For a transcribed call, a single click SHALL copy the instance's research prompt, then the call's date, time and length, then the transcript as timestamped lines without speaker labels, ready to paste into ChatGPT. The caller's phone number SHALL be left out unless the user includes it for that copy. Copying SHALL work when the app is served over plain HTTP on the shop network. Before copying, the user SHALL be able to see exactly the text that will be copied, and the preview SHALL follow the phone-number choice.

#### Scenario: Copy a call
- **WHEN** a user clicks Copy for ChatGPT on a transcribed call
- **THEN** the clipboard holds the research prompt, the call details without the phone number, and the transcript as timestamped lines without speaker labels, and the app confirms the copy

#### Scenario: Include the number
- **WHEN** the user turns on "include phone number" before copying
- **THEN** the copied text also contains the caller number

#### Scenario: Preview the copied text
- **WHEN** a user opens a transcribed call
- **THEN** they can show the exact text Copy for ChatGPT will copy, with or without the phone number as chosen

#### Scenario: Browser blocks the clipboard
- **WHEN** the browser refuses programmatic clipboard access
- **THEN** the app shows the text selected in a box, so the user can copy it with Ctrl+C
