# Spec Delta

## ADDED Requirements

### Requirement: People screen in the admin area
The People screen SHALL live at `/admin/people` behind the admin login, next to Settings. Its API endpoints SHALL require an admin session like every other admin endpoint.

#### Scenario: Admin opens People
- **WHEN** the logged-in admin opens the admin area
- **THEN** the navigation shows People and Settings, and People lists every profile

#### Scenario: People without login
- **WHEN** someone opens `/admin/people` or calls a profile-management endpoint without an admin session
- **THEN** they are sent to the admin login, or the request is rejected, and no profile data is sent
