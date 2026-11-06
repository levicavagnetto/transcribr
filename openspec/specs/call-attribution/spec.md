# call-attribution Specification

## Purpose
Lets each instance define the people who use the phones and works out which of them were on each transcribed call, from the name said in the opening or by hand, so a person can filter the store's calls down to their own. Attribution is per call; it never says which person spoke which line. Voice is not used.

## Requirements

### Requirement: People profiles
The admin SHALL be able to create, edit and delete people profiles in the admin area. A profile has a display name and one or more name variants (spellings and nicknames the transcript might contain). No person-specific data SHALL be built into the application.

#### Scenario: Create a profile
- **WHEN** the admin creates a profile "Nolan" with variants "Nolan" and "Nolen"
- **THEN** the profile appears in the profile list and as a filter in the call list

#### Scenario: Delete a profile
- **WHEN** the admin deletes a profile
- **THEN** all its attributions are deleted, and its calls revert to Unassigned unless another person is attributed

### Requirement: Name evidence
A profile SHALL have name evidence in a call when one of its name variants appears in the transcript within the first 30 seconds of speech. A recorded message that plays on many calls, such as the store's greeting or hold message, SHALL NOT count toward those 30 seconds, and SHALL be found from the instance's own transcripts without configuration. Matching SHALL tolerate small spelling differences in the transcribed name.

#### Scenario: Name in greeting
- **WHEN** a call's transcript starts "Thanks for calling Tire Pros, this is Nolan"
- **THEN** the Nolan profile has name evidence for that call

#### Scenario: A repeated greeting with a name
- **WHEN** Nolan answers "Thanks for calling Tire Pros, this is Nolan" the same way on many calls
- **THEN** that line is never treated as a recorded message, and the Nolan profile has name evidence

#### Scenario: Name only late in the call
- **WHEN** a profile's name appears only after the first 30 seconds of speech
- **THEN** that profile has no name evidence for the call

#### Scenario: Greeting after the hold message
- **WHEN** a caller hears the store's recorded hold message for 70 seconds and then Nolan answers "this is Nolan"
- **THEN** the Nolan profile has name evidence for that call

### Requirement: Automatic attribution rules
After a call is Transcribed, each profile with name evidence SHALL be attributed to the call as Maybe with method name, recording the name heard and its time. Automatic matching SHALL NOT make an attribution Confident; only a person's decision does. A profile without name evidence SHALL get no automatic attribution.

#### Scenario: Name in the greeting
- **WHEN** Nolan's name is in the opening of a call
- **THEN** the call is attributed to Nolan as Maybe with method name, showing the name heard and its time

#### Scenario: Caller asks for someone by name
- **WHEN** the caller says "Is Nolan there?" in the opening
- **THEN** the call is attributed to Nolan as Maybe, not Confident, and a user can confirm or reject it

#### Scenario: Transferred call with two staff
- **WHEN** both Nolan's and another profiled person's names are in the opening
- **THEN** the call is attributed to both people as Maybe

#### Scenario: No evidence
- **WHEN** no profile's name is in the opening of a call
- **THEN** the call is Unassigned

### Requirement: Manual attribution wins
Users SHALL be able to mark a call as belonging to a person, or as not belonging to a person. Manual decisions SHALL override automatic ones and survive re-matching.

#### Scenario: Claim a missed call
- **WHEN** a user marks an Unassigned call as Nolan's
- **THEN** the call is attributed to Nolan as Confident with method manual

#### Scenario: Reject a wrong match
- **WHEN** a user marks a call as not Nolan's
- **THEN** Nolan's attribution is removed from that call and is not re-added by automatic matching

#### Scenario: Confirm a Maybe
- **WHEN** a user confirms a Maybe attribution for Nolan
- **THEN** it becomes Confident with method manual

### Requirement: Re-matching when profiles change
When a profile is created or deleted, or its name variants change, automatic attributions SHALL be recomputed for all transcribed calls from stored transcripts. No audio SHALL be re-downloaded, and manual decisions SHALL be kept.

#### Scenario: Profile added after calls were transcribed
- **WHEN** the admin adds Nolan's profile after 100 calls were already transcribed
- **THEN** those 100 calls are re-matched and calls with his name in the opening become Maybe for him, without any Ravon requests
