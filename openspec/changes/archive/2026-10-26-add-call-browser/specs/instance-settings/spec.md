# Spec Delta

## ADDED Requirements

### Requirement: Research prompt setting
The instance SHALL store a research prompt used by Copy for ChatGPT, with a default suited to a tire and auto shop, editable by the admin in the admin Settings screen. The prompt SHALL be 1 to 4,000 characters.

#### Scenario: Edit the research prompt
- **WHEN** the admin edits the research prompt and a user then copies a call
- **THEN** the copied text starts with the edited prompt

#### Scenario: Empty prompt
- **WHEN** the admin clears the prompt and saves
- **THEN** the change is rejected with a message, and the previous prompt stays

#### Scenario: Default prompt
- **WHEN** the instance is new
- **THEN** the prompt asks ChatGPT to list what the customer asked for, including their vehicle and any budget or constraints, and to research options that fit
