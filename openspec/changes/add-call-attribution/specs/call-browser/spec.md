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
A call's screen SHALL show each attributed person with confidence, method, the name heard and its time, and voice scores. Anyone on the shop network SHALL be able to claim the call for a person, reject a person, confirm a Maybe, and set "Speaker N is <person>", without logging in.

#### Scenario: Why a call is Nolan's
- **WHEN** a user opens a call attributed to Nolan by name and voice
- **THEN** the screen shows the name heard with its time and the voice score of the matching speaker

#### Scenario: Call actions without login
- **WHEN** a staff member who is not logged in as admin opens a call
- **THEN** they can claim, reject or confirm attributions and set "Speaker N is <person>"

### Requirement: Speaker names in Copy for ChatGPT
Text copied for ChatGPT SHALL use person names for speakers matched to a person, and generic labels for the others.

#### Scenario: Copy a matched call
- **WHEN** a user copies a call where Speaker 1 is a strong voice match for Nolan
- **THEN** the copied transcript labels Speaker 1's lines "Nolan" and the other speaker's lines with its generic label

### Requirement: Person filter in the call API
The call list API SHALL accept a person, Maybe or Unassigned filter, and SHALL return each call's attributions, so clients such as a future MCP server can list one person's calls.

#### Scenario: List a person's calls since a time
- **WHEN** a client lists Nolan's calls since a given time
- **THEN** it receives those calls with their attributions, in pages, with a cursor for the next page
