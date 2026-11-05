# call-transcription Specification

## Purpose
Turns a listed call's recording into a timestamped transcript with per-line voiceprints, reliably and in the background, for both automatic and user-requested jobs.

## Requirements

### Requirement: Call processing states
Every listed call SHALL have exactly one processing state: Not transcribed, Waiting, Processing, Transcribed, or Failed. A call's state SHALL be returned by its transcription request, and the status SHALL count calls by state. Reading any call's state comes with the call API in `add-call-browser`.

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

### Requirement: Timestamped transcript
Processing SHALL produce a transcript of time-stamped segments (lines). Segments SHALL NOT be assigned to speakers, and processing SHALL NOT run speaker separation or compute voice embeddings. No voice data and no audio SHALL be stored. The call's detected language and the model identity SHALL be recorded with the transcript.

#### Scenario: Two-person call
- **WHEN** a call between a staff member and a customer is processed
- **THEN** the transcript's segments carry start and end times and text, with no speaker labels and no stored voice data

#### Scenario: Silent or near-empty call
- **WHEN** a call contains no recognizable speech
- **THEN** it ends Transcribed with an empty transcript and a "no speech" marker, not Failed

### Requirement: Background processing without starving the server
Processing SHALL handle one call at a time, at lower CPU priority than the web API, so the web app stays responsive while transcription runs.

#### Scenario: Browsing during a backlog
- **WHEN** 50 calls are Waiting and a user opens the web app
- **THEN** pages and API reads respond within 2 seconds

### Requirement: Recognize profile names reliably
Transcription SHALL be biased toward recognizing the name variants configured in people profiles, so names are transcribed consistently. Profile changes SHALL apply to calls transcribed from then on.

#### Scenario: Configured name in a greeting
- **WHEN** a staff member whose profile lists the name "Nolan" answers "Tire Pros, this is Nolan"
- **THEN** the transcript spells the name as configured

#### Scenario: New name variant
- **WHEN** the admin adds the variant "Nolen" to a profile
- **THEN** calls transcribed afterwards include it in the name hints, and earlier transcripts are unchanged
