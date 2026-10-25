# Spec Delta

## Purpose

Keeps the instance's configuration behind a single admin login at its own address, while the rest of the web app stays open to everyone on the shop network.

## ADDED Requirements

### Requirement: Admin area at its own address
Admin screens, starting with Settings, SHALL live under `/admin` and SHALL require the admin login. The API endpoints behind them SHALL also require the login, checked by the server on every request. The address being separate is not, by itself, protection.

#### Scenario: Not logged in
- **WHEN** someone opens `/admin/settings` without being logged in as admin
- **THEN** they see the admin login page, and no admin data is sent to the browser

#### Scenario: Calling an admin endpoint directly
- **WHEN** a request without a valid admin session calls an admin API endpoint, read or write
- **THEN** it is rejected with an authentication error and nothing changes

#### Scenario: Logged in
- **WHEN** the admin logs in
- **THEN** the admin screens open, and the navigation shows links to them, Back to the main app, and a Log out button

### Requirement: Create the admin on first visit with a setup code
While no admin account exists, the instance SHALL generate a one-time setup code and write it to the server log. The first visit to `/admin` SHALL ask for that code, then for a new admin username and password. The code SHALL stop working once the admin is created.

#### Scenario: First visit
- **WHEN** someone opens `/admin` on an instance with no admin account
- **THEN** they are asked for the setup code shown in the server log, and they can only choose a username and password after entering the correct code

#### Scenario: Wrong setup code
- **WHEN** someone enters an incorrect setup code
- **THEN** no account is created, and repeated wrong codes are slowed down as for logins

#### Scenario: Code used up
- **WHEN** an admin account has been created
- **THEN** the setup page is no longer reachable, and the old code no longer works

### Requirement: Admin password rules and storage
The admin password SHALL be at least 12 characters and SHALL be stored only as a slow, salted hash. Neither the password nor the hash SHALL be returned by any API or written to logs or backups in readable form.

#### Scenario: Short password
- **WHEN** someone tries to set an 8-character admin password
- **THEN** it is rejected with a message giving the minimum length

### Requirement: Admin sessions
After logging in, the admin SHALL stay logged in in that browser for up to 12 hours, or until they log out. Admin changes SHALL be accepted only from the app's own pages, so another website cannot make the admin's browser change settings.

#### Scenario: Session expires
- **WHEN** 12 hours pass after the admin logged in
- **THEN** the next admin page or admin request asks them to log in again

#### Scenario: Log out
- **WHEN** the admin clicks Log out
- **THEN** the session ends on the server, and admin pages ask for the login again

#### Scenario: Request from another site
- **WHEN** a page on another website tries to send an admin change using the admin's browser
- **THEN** the instance rejects it and nothing changes

### Requirement: Slow down repeated failed logins
The instance SHALL limit failed admin login and setup-code attempts per client, with increasing delays, and SHALL record failed attempts in the log without the passwords tried.

#### Scenario: Password guessing
- **WHEN** a client fails the admin login 5 times within a minute
- **THEN** further attempts from that client are refused for a growing period, and the failures are logged

### Requirement: Change and reset the admin password
The logged-in admin SHALL be able to change the password by entering the current one. An operator with access to the server SHALL be able to reset the admin account from the command line, which ends all admin sessions and starts the setup-code flow again.

#### Scenario: Change password
- **WHEN** the admin enters the current password and a valid new one
- **THEN** the new password works, the old one stops working, and other admin sessions end

#### Scenario: Forgotten password
- **WHEN** an operator runs the documented reset command on the server
- **THEN** the admin account is removed, the command prints a new setup code, and the next visit to `/admin` starts first-time setup
