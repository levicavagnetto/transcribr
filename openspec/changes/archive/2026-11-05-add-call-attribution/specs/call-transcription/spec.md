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

## MODIFIED Requirements

### Requirement: Timestamped transcript
Processing SHALL produce a transcript of time-stamped segments (lines). Segments SHALL NOT be assigned to speakers, and processing SHALL NOT run speaker separation or compute voice embeddings. No voice data and no audio SHALL be stored. The call's detected language and the model identity SHALL be recorded with the transcript.

#### Scenario: Two-person call
- **WHEN** a call between a staff member and a customer is processed
- **THEN** the transcript's segments carry start and end times and text, with no speaker labels and no stored voice data

#### Scenario: Silent or near-empty call
- **WHEN** a call contains no recognizable speech
- **THEN** it ends Transcribed with an empty transcript and a "no speech" marker, not Failed

## REMOVED Requirements

### Requirement: Per-speaker voice fingerprints
**Reason**: Speaker labels were not close to correct on real calls, and voice matching could not tell the shop's service writers apart on 8 kHz phone audio (`add-call-attribution` design D3).
**Migration**: Fingerprints and line voiceprints are dropped by migration. Attribution uses names in the transcript and manual decisions.
