# Spec Delta

## Purpose

Gives staff on the shop network one place to find, read and listen to the store's calls, filtered to a person, and to hand a call to ChatGPT. Exposes the same data through a REST API that the planned MCP server will use.

## ADDED Requirements

### Requirement: Shop-network web app
The web app SHALL be served by the instance on the shop network and work in current desktop browsers without installing anything. Everyone who can reach it SHALL see all calls and use every action on the call list and call screen without logging in. The People and Settings screens live in the admin area (see `admin-access`) and are not shown in the normal navigation.

#### Scenario: Open the app
- **WHEN** a staff member opens the instance's address in a browser on the shop network
- **THEN** the call list loads, newest first, with no login

#### Scenario: Call actions without login
- **WHEN** a staff member who is not logged in as admin opens a call
- **THEN** they can listen, copy for ChatGPT, transcribe or retry, claim, reject or confirm an attribution, and set "Speaker N is <person>"

#### Scenario: Admin screens not in the normal navigation
- **WHEN** a staff member uses the app without the admin login
- **THEN** the navigation shows no People or Settings links, and the only way in is a small "Admin" link in the page footer that opens `/admin`

### Requirement: Call list with filters
The call list SHALL show each call's start time, length, caller number, answered-by text, processing state and attributed people (Confident or Maybe). It SHALL filter by person, Unassigned, Maybe, processing state and date range, and combine filters.

#### Scenario: Filter to one person
- **WHEN** a user selects the Nolan filter
- **THEN** only calls attributed to Nolan (Confident or Maybe) are shown, with Maybe calls marked

#### Scenario: Review uncertain calls
- **WHEN** a user selects the Maybe filter
- **THEN** only calls with at least one Maybe attribution are shown

#### Scenario: Missed calls
- **WHEN** a user filters by Not transcribed
- **THEN** calls missed while the server was off are shown, each with a Transcribe button

### Requirement: Text and number search
Users SHALL be able to search transcripts by words and calls by caller number, combined with the filters.

#### Scenario: Search a phrase within a person's calls
- **WHEN** a user filters to Nolan and searches "lift kit"
- **THEN** Nolan's calls whose transcript contains "lift kit" are shown, with the matching text highlighted

#### Scenario: Search a caller number
- **WHEN** a user searches a phone number, with or without punctuation
- **THEN** calls from that number are shown, transcribed or not

### Requirement: Call detail
Opening a call SHALL show its details, its attributions with method and confidence, and the transcript with timestamps and speaker names. It SHALL also show the actions available for the call's state.

#### Scenario: Transcribed call
- **WHEN** a user opens a Transcribed call
- **THEN** the transcript is shown with speaker names, along with the Copy for ChatGPT, Listen, attribution and enrollment actions

#### Scenario: Failed call
- **WHEN** a user opens a Failed call
- **THEN** the failure reason and a Retry button are shown

### Requirement: Copy for ChatGPT
For a transcribed call, a single click SHALL copy the instance's research prompt followed by the call's date, time, length and speaker-labeled transcript to the clipboard, ready to paste into ChatGPT. The caller's phone number SHALL be omitted unless the user includes it for that copy.

#### Scenario: Copy a call
- **WHEN** a user clicks Copy for ChatGPT on a transcribed call
- **THEN** the clipboard holds the research prompt, the call details without the phone number, and the transcript with speaker names, and the app confirms the copy

#### Scenario: Include the number
- **WHEN** the user turns on "include phone number" before copying
- **THEN** the copied text also contains the caller number

### Requirement: Listen through the server
Users SHALL be able to play a call's recording in the browser. The audio is streamed from Ravon through the instance, so no Ravon login is needed in the browser and nothing is saved.

#### Scenario: Play a recording
- **WHEN** a user clicks Listen on a call
- **THEN** the recording plays in the browser, and no copy of the audio is stored by the instance

### Requirement: Live updates
The call list and open call SHALL reflect new calls, state changes and attribution changes within 30 seconds, without a manual reload.

#### Scenario: New call appears
- **WHEN** a new call is listed while a user has the call list open
- **THEN** it appears in the list within 30 seconds

### Requirement: Light and dark themes
The web app SHALL offer a light and a dark theme built from the same colour palette. It SHALL follow the device's light or dark setting by default and offer a Light / Dark / System choice. The choice is remembered per browser and is not an instance setting. Text and controls SHALL meet 4.5:1 contrast in both themes.

#### Scenario: Device set to dark
- **WHEN** a user with a dark device setting opens the app for the first time
- **THEN** the app is shown in the dark theme, with no flash of the light theme while loading

#### Scenario: Override the device setting
- **WHEN** a user picks Light in the theme menu and reloads the page
- **THEN** the app stays light in that browser, and other browsers keep their own choice

#### Scenario: Readable in both themes
- **WHEN** any screen is shown in either theme
- **THEN** body text, labels, chips, links and button text meet a contrast ratio of at least 4.5:1 against their background

### Requirement: Service status banner
The web app SHALL show a banner when the instance needs attention: the Ravon login failed, Ravon is unreachable, the worker has stopped, or allow-list violations were recorded.

#### Scenario: Login failed
- **WHEN** Ravon rejects the instance's credentials
- **THEN** every page shows a banner saying the Ravon login failed and how to fix it

### Requirement: REST API for clients
All data and actions in the web app SHALL be available through a documented REST API with a machine-readable OpenAPI description. Every read SHALL be a GET with no side effects. Every change SHALL use a non-GET method, so a future client such as the MCP server can be restricted to reads.

#### Scenario: Reads have no side effects
- **WHEN** a client calls any GET endpoint
- **THEN** no call, job, attribution, profile or setting changes, and no request is sent to Ravon except the audio stream for Listen

#### Scenario: List calls through the API
- **WHEN** a client lists a person's calls since a given time
- **THEN** it receives those calls with their attributions and transcript availability, in pages, with a cursor for the next page

#### Scenario: OpenAPI description
- **WHEN** a client requests the API description
- **THEN** it receives an OpenAPI document covering every endpoint, with request and response schemas
