# Spec Delta

## Purpose

The web app shell every Transcribr screen lives in: served on the shop network without a login, themed, showing the instance's health, with the admin area reachable from a small link in the top bar and a REST API every screen and future client uses.

## ADDED Requirements

### Requirement: Shop-network web app
The web app SHALL be served by the instance on the shop network and work in current desktop browsers without installing anything. Everyone who can reach it SHALL use the non-admin screens without logging in. Admin screens live in the admin area (see `admin-access`) and SHALL NOT appear in the normal navigation.

#### Scenario: Open the app
- **WHEN** a staff member opens the instance's address in a browser on the shop network
- **THEN** the home page loads with no login

#### Scenario: Admin screens not in the normal navigation
- **WHEN** a staff member uses the app without the admin login
- **THEN** the navigation shows no admin screens, and the only way in is a small "Admin" link in the top bar that opens `/admin`, which stays on screen however long the page is

### Requirement: Collection status on the home page
The home page SHALL show what the instance is collecting: the time of the last successful check, and how many calls were listed and transcribed today, Waiting, and Failed.

#### Scenario: Working instance
- **WHEN** the worker has checked Ravon within the poll interval and transcribed 12 of today's 15 listed calls
- **THEN** the home page shows the last check time, 15 listed and 12 transcribed today, and the Waiting and Failed counts

#### Scenario: First setup not done
- **WHEN** no store queue has been chosen yet
- **THEN** the home page says the admin must choose store queues at `/admin/settings`

### Requirement: Light and dark themes
The web app SHALL offer a light and a dark theme built from the same colour palette. It SHALL follow the device's light or dark setting by default and offer a Light / Dark / System choice. The choice is remembered per browser and is not an instance setting. Text and controls SHALL meet 4.5:1 contrast in both themes.

#### Scenario: Device set to dark
- **WHEN** a user with a dark device setting opens the app for the first time
- **THEN** the app is shown in the dark theme, with no flash of the light theme while loading

#### Scenario: Device setting changes while open
- **WHEN** the device switches between light and dark while the app is open
- **THEN** the app follows within a second, without a reload, unless the user picked Light or Dark

#### Scenario: Override the device setting
- **WHEN** a user picks Light in the theme menu and reloads the page
- **THEN** the app stays light in that browser, and other browsers keep their own choice

#### Scenario: Other apps on the same address
- **WHEN** another web app on the same address has saved its own light or dark choice in the browser
- **THEN** Transcribr ignores it and follows the device setting or its own saved choice

#### Scenario: Readable in both themes
- **WHEN** any screen is shown in either theme
- **THEN** body text, labels, chips, links and button text meet a contrast ratio of at least 4.5:1 against their background

### Requirement: Service status banner
The web app SHALL show a banner on every page when the instance needs attention: the Ravon login failed, Ravon is unreachable, Ravon credentials are missing, the worker has stopped, or allow-list violations were recorded.

#### Scenario: Login failed
- **WHEN** Ravon rejects the instance's credentials
- **THEN** every page shows a banner saying the Ravon login failed and how to fix it

#### Scenario: Healthy
- **WHEN** nothing needs attention
- **THEN** no banner is shown

### Requirement: REST API for clients
All data and actions in the web app SHALL be available through a documented REST API with a machine-readable OpenAPI description. Every read SHALL be a GET with no side effects. Every change SHALL use a non-GET method, so a future client such as the MCP server can be restricted to reads.

#### Scenario: Reads have no side effects
- **WHEN** a client calls any GET endpoint
- **THEN** no call, job or setting changes, and no request is sent to Ravon, except where a GET endpoint is documented as streaming a recording from Ravon

#### Scenario: OpenAPI description
- **WHEN** a client requests the API description
- **THEN** it receives an OpenAPI document covering every endpoint, with request and response schemas

#### Scenario: Request transcription through the API
- **WHEN** a client sends the transcribe action for a Not transcribed call
- **THEN** the call becomes Waiting, as described in `call-transcription`
