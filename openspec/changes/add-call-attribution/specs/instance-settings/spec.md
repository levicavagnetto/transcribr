# Spec Delta

## ADDED Requirements

### Requirement: Voice matching thresholds
The instance SHALL store a low and a high voice-similarity threshold, editable by the admin in the admin Settings screen. Both SHALL be between 0 and 1, with low below high. The defaults SHALL come from calibration on real calls.

#### Scenario: Thresholds changed
- **WHEN** the admin changes a voice threshold
- **THEN** automatic attributions are recomputed for all transcribed calls, per the `call-attribution` rules

#### Scenario: Invalid thresholds
- **WHEN** the admin sets the low threshold above the high one
- **THEN** the change is rejected with a message, and the previous values stay
