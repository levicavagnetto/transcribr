# Spec Delta

## Purpose

Collects the store's call list and recording audio from the Ravon admin site, without ever changing anything on Ravon, and decides which newly seen calls are transcribed automatically.

## ADDED Requirements

### Requirement: Read-only request allow list
Every request the system sends to Ravon SHALL pass an allow list before it is sent. The list permits only: the login page and login form submit, the recordings search page and its search submit (search fields only), the queue list read from that page, and recording audio for IDs seen in search results. Anything else SHALL be refused without being sent, and the refusal SHALL be logged without form values.

#### Scenario: Search request with only search fields
- **WHEN** the system submits a recordings search containing only the search fields and a date range
- **THEN** the request is sent

#### Scenario: Request carrying a delete or selection field
- **WHEN** any code attempts a request to Ravon that includes a field named `checked`, `delete`, `deleteAll`, or any field not on the allow list
- **THEN** the request is not sent, an allow-list violation is recorded, and the attempt is logged with method and path only

#### Scenario: Request to a path not on the list
- **WHEN** any code attempts a request to a Ravon path not on the allow list, including any live-call tool or the `ajax.html` endpoint
- **THEN** the request is not sent and an allow-list violation is recorded

#### Scenario: Audio for an unknown recording ID
- **WHEN** audio is requested for a recording ID that has not appeared in a search result
- **THEN** the request is not sent

### Requirement: Session login and re-login
The system SHALL log in to Ravon with the credentials provided by the deployment environment. It SHALL reuse the session while Ravon accepts it, and log in again automatically when Ravon rejects it. Credentials SHALL never be logged or returned by any API.

#### Scenario: Session expired
- **WHEN** a Ravon request is redirected to the login page
- **THEN** the system logs in once and retries the request once

#### Scenario: Credentials rejected
- **WHEN** a login attempt is rejected by Ravon
- **THEN** the system stops attempting logins, reports a "Ravon login failed" status, and does not retry until the credentials change or an operator requests a retry

### Requirement: Date-bounded searches only
Every recordings search SHALL include a start and end date-time, with a span of at most 7 days.

#### Scenario: Search window too wide
- **WHEN** a search is requested for a span longer than 7 days
- **THEN** it is split into consecutive searches of at most 7 days each, or refused if splitting is not possible

### Requirement: Poll for new calls
While running, the system SHALL search Ravon for each configured store queue at the configured poll interval. The search window SHALL reach back far enough to catch calls that finished since the last successful poll. Calls are identified by recording ID and SHALL be listed once, however many searches return them.

#### Scenario: New call appears
- **WHEN** a poll returns a recording ID the system has not seen
- **THEN** the call is listed with its start time, length, caller number, answered-by text and queue

#### Scenario: Call returned by overlapping searches
- **WHEN** the same recording ID is returned by two polls or two queues
- **THEN** only one call record exists

#### Scenario: Empty result
- **WHEN** a search returns no calls
- **THEN** the poll is treated as successful, not as an error

### Requirement: Automatic transcription only for calls that ended while the server was running
A newly listed call SHALL be queued for automatic transcription only if its end time (start time plus length) falls within a period when the server was running. All other newly listed calls SHALL be listed as Not transcribed and SHALL NOT be queued automatically. A Ravon outage while the server is running does not count as the server being off.

#### Scenario: Call ends while the server is running
- **WHEN** the server has been running continuously since before a call ended, and a poll then lists that call
- **THEN** the call is queued for automatic transcription

#### Scenario: Call ends while the server is off
- **WHEN** the server was stopped when a call ended, and the call is listed after the server starts again
- **THEN** the call is listed as Not transcribed and is not queued

#### Scenario: Ravon unreachable for a while
- **WHEN** the server is running but Ravon is unreachable for 20 minutes, and calls that ended during that time are listed once Ravon is reachable again
- **THEN** those calls are queued for automatic transcription

#### Scenario: First start
- **WHEN** the server starts for the first time
- **THEN** calls from the previous 7 days are listed as Not transcribed and none are queued automatically

### Requirement: Catch up the call list after downtime
On start, the system SHALL list the calls that occurred while it was off, from shortly before the newest known call up to now, without queuing them. Users SHALL be able to load older calls in 7-day steps on request.

#### Scenario: Restart after a weekend off
- **WHEN** the server starts after being off for two days
- **THEN** the calls from those two days are listed as Not transcribed

#### Scenario: Load earlier calls
- **WHEN** a user asks to load earlier calls
- **THEN** the system lists the 7 days before the oldest listed call, without queuing them

### Requirement: Fetch recording audio into memory
The system SHALL download a recording's audio into memory, check that the byte count matches the declared length, and never write recording audio to disk.

#### Scenario: Truncated download
- **WHEN** the downloaded byte count differs from the declared length
- **THEN** the download is treated as failed and retried under the job retry rules

#### Scenario: No audio on disk
- **WHEN** any number of calls have been processed
- **THEN** no recording audio exists in the data volume or the container's file system

### Requirement: Polite load on Ravon
The system SHALL send Ravon requests one at a time, with a minimum delay between requests. On repeated failures it SHALL back off, with a ceiling on the delay.

#### Scenario: Ravon returns server errors
- **WHEN** five consecutive Ravon requests fail with server errors or timeouts
- **THEN** the system pauses Ravon requests with increasing delays, reports a "Ravon unreachable" status, and resumes normal polling after the next success
