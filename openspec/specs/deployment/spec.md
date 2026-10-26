# deployment Specification

## Purpose
Makes an instance easy to install, run unattended, update and move on any machine with Docker, while keeping its data safe across restarts and updates.

## Requirements

### Requirement: Runs from one container image
The instance SHALL be started from a single container image, built on the host from the project folder, with one compose file and one environment file. No other software needs to be installed on the host except Docker. Publishing the image to a registry is later work. The image SHALL be available for amd64 (64-bit Intel or AMD processors) and run on Linux, Windows (Docker Desktop with WSL2) and macOS on Intel. ARM hosts are not supported.

#### Scenario: Fresh install
- **WHEN** an operator places the project folder with an environment file holding the Ravon credentials on a host with Docker, and runs the start command
- **THEN** the image is built and the web app becomes reachable on the configured port, with no further installation steps

#### Scenario: Intel or AMD host
- **WHEN** the compose file is used on a 64-bit Intel or AMD host
- **THEN** the instance starts and transcribes calls with the bundled models

### Requirement: No downloads at runtime
The image SHALL contain every model and asset the instance needs. A running instance SHALL only make network requests to Ravon.

#### Scenario: Offline except for Ravon
- **WHEN** the host can reach Ravon but no other internet address
- **THEN** the instance starts, transcribes calls and matches voices normally

### Requirement: Persistent data in one volume
All instance data SHALL live in one named data volume: the database (calls, transcripts, voice fingerprints, settings and everything later features add), backups and logs. Removing and recreating the container SHALL lose nothing.

#### Scenario: Recreate the container
- **WHEN** the container is removed and started again from the same or a newer image
- **THEN** all instance data is present

#### Scenario: Back up and restore
- **WHEN** an operator runs the documented backup command and restores it on another host
- **THEN** the new instance has the same data as the old one

### Requirement: Unattended operation
The instance SHALL start when Docker starts and restart automatically after a crash. It SHALL report health to Docker, so an unhealthy instance can be seen and restarted. On Windows and macOS, Docker Desktop only starts when a user signs in, so there the host must sign a user in automatically.

#### Scenario: Host reboot
- **WHEN** the host restarts and Docker starts
- **THEN** the instance starts without anyone logging in or running a command

#### Scenario: Worker crash
- **WHEN** the transcription worker process crashes
- **THEN** it is restarted automatically, the web app keeps serving during the restart, and queued calls continue afterwards

### Requirement: Safe updates
Updating SHALL be getting the newer project version, then rebuilding and restarting with one command. Database schema changes SHALL be applied automatically on start. A failed schema change SHALL leave the data unchanged and stop the instance with a clear error.

#### Scenario: Update with a schema change
- **WHEN** an instance starts on a newer image that changes the database schema
- **THEN** the schema is upgraded once, a backup copy of the database is kept from before the upgrade, and the instance runs normally

### Requirement: Runs without elevated privileges
The container SHALL run as a non-root user, expose only the web port, and need no host devices or privileged mode.

#### Scenario: Inspect the running container
- **WHEN** an operator inspects the running container
- **THEN** its process runs as a non-root user, and only the web port is published
