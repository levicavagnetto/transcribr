# call-browser Specification

## Purpose
Gives staff on the shop network one place to find, read and listen to the store's calls, and to hand a call to ChatGPT for research.

## Requirements

### Requirement: Call list as the home page
The web app's home page SHALL be the call list, newest first, open to everyone on the shop network without a login. Each row SHALL show the call's start time, length, caller number, answered-by text and processing state. The collection figures (last check, Waiting, Failed) SHALL stay visible in the app's status area.

#### Scenario: Open the app
- **WHEN** a staff member opens the instance's address
- **THEN** the call list loads, newest first, with no login, and the last check time is visible

#### Scenario: First setup not done
- **WHEN** no store queue has been chosen yet
- **THEN** the call list says the admin must choose store queues at `/admin/settings`

#### Scenario: Many calls
- **WHEN** more calls exist than fit on one page
- **THEN** older calls load as the user scrolls or pages, without re-sending earlier rows

#### Scenario: Reach the oldest listed call
- **WHEN** a user scrolls to the end of the listed calls
- **THEN** the list offers to list the week before from Ravon

### Requirement: Filter by state and date
The call list SHALL filter by processing state (any, Transcribed, Waiting, Processing, Not transcribed, Failed) and by date range. Filters SHALL combine with each other and with search.

#### Scenario: Missed calls
- **WHEN** a user filters by Not transcribed
- **THEN** only calls missed while the server was off are shown, each with a Transcribe button

#### Scenario: Date range
- **WHEN** a user picks Oct 15 to Oct 22
- **THEN** only calls that started in that range, in the store's time zone, are shown

### Requirement: Text and number search
Users SHALL be able to search transcripts by words and calls by caller number. Number search SHALL ignore punctuation and spaces. Text matches SHALL show the matching passage with the matched words highlighted.

#### Scenario: Search a phrase
- **WHEN** a user searches "lift kit"
- **THEN** calls whose transcript contains "lift kit" are shown, each with the matching passage and its time in the call

#### Scenario: Search a caller number
- **WHEN** a user searches "405 555 0142" or "(405) 555-0142"
- **THEN** calls from that number are shown, transcribed or not

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

### Requirement: Listen through the server
Users SHALL be able to play a call's recording in the browser. The audio SHALL be streamed from Ravon through the instance, so no Ravon login is needed in the browser, and nothing is saved.

#### Scenario: Play a recording
- **WHEN** a user clicks Listen on a call
- **THEN** the recording plays in the browser, and no copy of the audio is stored by the instance

#### Scenario: Ravon unavailable
- **WHEN** a user clicks Listen while Ravon is unreachable
- **THEN** the app says the recording can't be fetched from Ravon right now

### Requirement: Live updates
The call list and the open call SHALL reflect new calls and state changes within 30 seconds, without a manual reload.

#### Scenario: New call appears
- **WHEN** a new call is listed while a user has the call list open
- **THEN** it appears in the list within 30 seconds

#### Scenario: Transcription finishes
- **WHEN** a call the user has open finishes transcribing
- **THEN** its transcript appears within 30 seconds

### Requirement: Check Ravon now
The call list SHALL offer a "Check Ravon now" button, open to everyone, that makes the worker check Ravon for new calls right away instead of at the next scheduled check. Presses within 15 seconds of the last check SHALL NOT cause another Ravon check. While the check is pending the button SHALL show that it is checking, and calls it finds SHALL appear without a reload, marked as new.

#### Scenario: Check now
- **WHEN** a user presses Check Ravon now while the worker is idle
- **THEN** a check runs within 5 seconds, the last check time updates, and any new calls appear in the list

#### Scenario: Several presses
- **WHEN** several users press it within 15 seconds
- **THEN** Ravon is checked once

#### Scenario: Worker busy
- **WHEN** the button is pressed while the worker is transcribing a call
- **THEN** the check runs as soon as that call finishes, and the button says it is waiting for the current transcription

#### Scenario: Worker stopped
- **WHEN** the worker isn't running
- **THEN** the button is disabled and says why

### Requirement: Call API for clients
The call list, call detail and transcript SHALL be available as GET endpoints with cursor paging, and the actions as non-GET endpoints. The API SHALL never return voice fingerprints.

#### Scenario: List calls since a time
- **WHEN** a client lists calls started since a given time
- **THEN** it receives them with their state and transcript availability, in pages, with a cursor for the next page

#### Scenario: No fingerprints
- **WHEN** a client reads any call or transcript endpoint
- **THEN** the response contains no voice fingerprint data

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
A call's screen SHALL show each attributed person with confidence, method, and for automatic matches the name heard and its time. Anyone on the shop network SHALL be able to claim the call for a person, reject a person, and confirm a Maybe, without logging in.

#### Scenario: Why a call is Nolan's
- **WHEN** a user opens a call attributed to Nolan by name
- **THEN** the screen shows Nolan as Maybe, with the name heard and its time

#### Scenario: Call actions without login
- **WHEN** a staff member who is not logged in as admin opens a call
- **THEN** they can claim, reject or confirm attributions

### Requirement: Person filter in the call API
The call list API SHALL accept a person, Maybe or Unassigned filter, and SHALL return each call's attributions, so clients such as a future MCP server can list one person's calls.

#### Scenario: List a person's calls since a time
- **WHEN** a client lists Nolan's calls since a given time
- **THEN** it receives those calls with their attributions, in pages, with a cursor for the next page
