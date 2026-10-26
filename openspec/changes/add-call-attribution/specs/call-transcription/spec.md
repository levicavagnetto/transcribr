# Spec Delta

## ADDED Requirements

### Requirement: Recognize profile names reliably
Transcription SHALL be biased toward recognizing the name variants configured in people profiles, so names are transcribed consistently. Profile changes SHALL apply to calls transcribed from then on.

#### Scenario: Configured name in a greeting
- **WHEN** a staff member whose profile lists the name "Nolan" answers "Tire Pros, this is Nolan"
- **THEN** the transcript spells the name as configured

#### Scenario: New name variant
- **WHEN** the admin adds the variant "Nolen" to a profile
- **THEN** calls transcribed afterwards include it in the name hints, and earlier transcripts are unchanged

## RENAMED Requirements

- FROM: `### Requirement: Speaker-labeled transcript`
- TO: `### Requirement: Timestamped transcript`

- FROM: `### Requirement: Per-speaker voice fingerprints`
- TO: `### Requirement: Per-line voiceprints`

## MODIFIED Requirements

### Requirement: Timestamped transcript
Processing SHALL produce a transcript of time-stamped segments (lines). Segments SHALL NOT be assigned to speakers, and processing SHALL NOT run speaker separation. The call's detected language and the model identity SHALL be recorded with the transcript.

#### Scenario: Two-person call
- **WHEN** a call between a staff member and a customer is processed
- **THEN** the transcript's segments carry start and end times and text, with no speaker labels

#### Scenario: Silent or near-empty call
- **WHEN** a call contains no recognizable speech
- **THEN** it ends Transcribed with an empty transcript and a "no speech" marker, not Failed

### Requirement: Per-line voiceprints
For each transcript line of at least 1 second, processing SHALL store a voiceprint of that line's audio. No audio SHALL be stored. Voiceprints SHALL never be returned by any API.

#### Scenario: Voiceprints stored without audio
- **WHEN** a call is Transcribed
- **THEN** each line of 1 second or more has a stored voiceprint, shorter lines have none, and no audio of the call is stored

#### Scenario: API never exposes voiceprints
- **WHEN** any API endpoint returns a call or its transcript
- **THEN** the response contains no voiceprint data
