# Spec Delta

## Purpose

Turns a listed call's recording into a speaker-labeled transcript with per-speaker voice fingerprints, reliably and in the background, for both automatic and user-requested jobs.

## ADDED Requirements

### Requirement: Call processing states
Every listed call SHALL have exactly one processing state: Not transcribed, Waiting, Processing, Transcribed, or Failed. The state SHALL be visible through the API.

#### Scenario: Automatic call moves through states
- **WHEN** a call is queued automatically and processing succeeds
- **THEN** its state goes from Waiting to Processing to Transcribed

#### Scenario: Failed call
- **WHEN** processing a call fails after all retries
- **THEN** its state is Failed, with a human-readable reason

### Requirement: Manual transcription request
A user SHALL be able to request transcription of any call that is Not transcribed or Failed. A request for a call that is already Waiting, Processing or Transcribed SHALL change nothing.

#### Scenario: Transcribe a missed call
- **WHEN** a user requests transcription of a Not transcribed call
- **THEN** the call becomes Waiting and is processed like an automatic job

#### Scenario: Duplicate request
- **WHEN** a user requests transcription of a call that is already Waiting
- **THEN** no second job is created

### Requirement: Durable job queue
Queued work SHALL survive process restarts, container restarts and host reboots. A call that was Processing when the worker stopped SHALL return to Waiting when the worker starts again.

#### Scenario: Worker killed mid-call
- **WHEN** the worker process is killed while a call is Processing, and then restarted
- **THEN** that call is processed again from the start and ends Transcribed or Failed, never stuck in Processing

### Requirement: Retries with backoff
A failed processing attempt SHALL be retried up to 3 times with increasing delays. Failures caused by Ravon being unreachable or logged out SHALL wait for Ravon to recover and SHALL NOT use up the call's retries.

#### Scenario: Transient download failure
- **WHEN** the audio download fails once, then succeeds on retry
- **THEN** the call ends Transcribed

#### Scenario: Ravon login failing
- **WHEN** Ravon credentials are rejected while calls are Waiting
- **THEN** those calls stay Waiting, with their retry counts unchanged, until Ravon access works again

#### Scenario: Retry a failed call
- **WHEN** a user requests transcription of a Failed call
- **THEN** it becomes Waiting with a fresh retry count

### Requirement: Speaker-labeled transcript
Processing SHALL produce a transcript of time-stamped segments, each assigned to a speaker label within the call (for example Speaker 1, Speaker 2). The call's detected language and the model identity SHALL be recorded with the transcript.

#### Scenario: Two-person call
- **WHEN** a call between a staff member and a customer is processed
- **THEN** the transcript's segments carry start and end times and are split between two speaker labels

#### Scenario: Silent or near-empty call
- **WHEN** a call contains no recognizable speech
- **THEN** it ends Transcribed with an empty transcript and a "no speech" marker, not Failed

### Requirement: Per-speaker voice fingerprints
For each speaker in a transcribed call, processing SHALL store a voice fingerprint and the seconds of speech it came from. No audio SHALL be stored. Fingerprints SHALL never be returned by any API.

#### Scenario: Fingerprints stored without audio
- **WHEN** a call is Transcribed
- **THEN** each speaker label has a stored fingerprint and speech duration, and no audio of the call is stored

#### Scenario: API never exposes fingerprints
- **WHEN** any API endpoint returns a call or its speakers
- **THEN** the response contains no voice fingerprint data

### Requirement: Background processing without starving the server
Processing SHALL handle one call at a time, at lower CPU priority than the web API, so the web app stays responsive while transcription runs.

#### Scenario: Browsing during a backlog
- **WHEN** 50 calls are Waiting and a user opens the web app
- **THEN** pages and API reads respond within 2 seconds
