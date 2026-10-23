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
