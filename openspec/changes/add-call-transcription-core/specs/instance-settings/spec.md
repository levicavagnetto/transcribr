# Spec Delta

## Purpose

Lets each instance be set up for its own store and people from the web app, keeps that configuration with the instance's data, and reports whether the instance is healthy.

## ADDED Requirements

### Requirement: Settings stored with the instance
All settings SHALL be stored in the instance's data volume and survive restarts and image updates. Settings SHALL be editable only by the admin, in the admin area (see `admin-access`), and take effect without a restart.

#### Scenario: Change the poll interval
- **WHEN** the admin changes the poll interval from 2 minutes to 5 minutes
- **THEN** the next poll happens about 5 minutes after the previous one, without restarting the instance

#### Scenario: Update the image
- **WHEN** the instance is updated to a new image version
- **THEN** all settings, profiles, calls and transcripts are still present

### Requirement: Store queues
The admin SHALL choose which Ravon queues the instance follows, from the queue list read from Ravon. At least one queue SHALL be selected before polling starts.

#### Scenario: First setup
- **WHEN** the instance starts with valid Ravon credentials and no queues selected
- **THEN** the call list shows a banner saying the admin must choose store queues at `/admin/settings`, the admin Settings screen shows the Ravon queue list, and no polling happens until a queue is chosen

#### Scenario: Add a queue later
- **WHEN** the admin adds a queue
- **THEN** the next poll includes it, and its earlier calls are listed as Not transcribed and not queued

### Requirement: Adjustable settings
The instance SHALL provide settings with defaults for: the poll interval (default 2 minutes, range 1–30), the store time zone, the research prompt used by Copy for ChatGPT, and the voice matching low and high thresholds. Out-of-range values SHALL be rejected with a message.

#### Scenario: Edit the research prompt
- **WHEN** the admin edits the research prompt and copies a call
- **THEN** the copied text starts with the edited prompt

#### Scenario: Invalid value
- **WHEN** the admin enters a poll interval of 0
- **THEN** the change is rejected with a message giving the allowed range

#### Scenario: Thresholds changed
- **WHEN** the admin changes a voice threshold
- **THEN** automatic attributions are recomputed, per the call attribution rules

### Requirement: Secrets from the environment
The Ravon username and password SHALL be supplied by the deployment environment, not entered or stored through the web app. Settings screens and the API SHALL show only whether credentials are present and working.

#### Scenario: Credentials missing
- **WHEN** the instance starts without Ravon credentials in its environment
- **THEN** it keeps serving the web app, does not contact Ravon, and shows a banner explaining which environment values to set

#### Scenario: Password never exposed
- **WHEN** any settings screen, API response or log line is produced
- **THEN** it does not contain the Ravon password or session cookies

### Requirement: Service status
The instance SHALL report its health through the API and the web app. The report covers worker running or stopped, last successful poll time, Ravon state (ok, login failed, unreachable, no credentials), queue length, calls failed in the last 24 hours, and allow-list violation count.

#### Scenario: Healthy instance
- **WHEN** everything is working
- **THEN** the status shows the worker running, Ravon ok, the last poll within the poll interval, and the queue length

#### Scenario: Worker stopped
- **WHEN** the worker has not reported in for 3 minutes
- **THEN** the status shows the worker stopped, and the web app banner appears
