# Spec Delta

## Purpose

Lets each instance define the people who use the phones and assigns transcribed calls to them by name, by voice, or by hand, so a person can filter the store's calls down to their own.

## ADDED Requirements

### Requirement: People profiles
The admin SHALL be able to create, edit and delete people profiles in the admin area. A profile has a display name and one or more name variants (spellings and nicknames the transcript might contain). No person-specific data SHALL be built into the application.

#### Scenario: Create a profile
- **WHEN** the admin creates a profile "Nolan" with variants "Nolan" and "Nolen"
- **THEN** the profile appears in the profile list and as a filter in the call list

#### Scenario: Delete a profile
- **WHEN** the admin deletes a profile
- **THEN** its voice profile and all its automatic attributions are deleted, and its calls revert to Unassigned unless another person is attributed

### Requirement: Voice enrollment from existing calls
Any user SHALL be able to build a person's voice profile from the call screen by choosing, in a transcribed call, the speaker label that is that person. The admin SHALL be able to review and remove enrolled calls in the admin area. Voice matching for the person SHALL start only after at least 3 calls and 60 seconds of their speech are enrolled.

#### Scenario: Enroll from a call
- **WHEN** a user opens a transcribed call, picks "Speaker 1 is Nolan", and confirms
- **THEN** that speaker's fingerprint is added to Nolan's voice profile, and the profile shows the enrolled call count and seconds

#### Scenario: Not enough enrolled speech
- **WHEN** a profile has 2 enrolled calls totaling 40 seconds of speech
- **THEN** voice matching is not used for that profile, and the profile page says how much more is needed

#### Scenario: Remove an enrolled call
- **WHEN** the admin removes an enrolled call from a voice profile
- **THEN** the voice profile is rebuilt without it

### Requirement: Name evidence
A profile SHALL have name evidence in a call when one of its name variants appears in the transcript within the first 30 seconds of speech. Matching SHALL tolerate small spelling differences in the transcribed name.

#### Scenario: Name in greeting
- **WHEN** a call's transcript starts "Thanks for calling Tire Pros, this is Nolan"
- **THEN** the Nolan profile has name evidence for that call

#### Scenario: Name only late in the call
- **WHEN** a profile's name appears only after the first 30 seconds of speech
- **THEN** that profile has no name evidence for the call

### Requirement: Voice evidence
For each enrolled profile, voice similarity SHALL be computed between the profile and every speaker in a call. A speaker scoring at or above the instance's high threshold is a strong voice match. A score between the low and high thresholds is a weak voice match.

#### Scenario: Strong voice match
- **WHEN** a speaker's similarity to Nolan's voice profile is at or above the high threshold
- **THEN** Nolan has strong voice evidence for that call, tied to that speaker

### Requirement: Automatic attribution rules
After a call is Transcribed, each profile SHALL be attributed to the call as Confident or Maybe, or not at all. The rules are:
- Strong voice: Confident.
- Name with strong or weak voice: Confident.
- Name with no voice profile yet: Confident.
- Name where the voice profile matches no speaker even weakly: Maybe.
- Weak voice alone: Maybe.
Each attribution SHALL record its method (name, voice, name+voice) and its scores.

#### Scenario: Name and voice agree
- **WHEN** Nolan's name is in the opening and one speaker is a weak or strong voice match for Nolan
- **THEN** the call is attributed to Nolan as Confident with method name+voice

#### Scenario: Outbound call without a name
- **WHEN** Nolan's name is never said but one speaker is a strong voice match for Nolan
- **THEN** the call is attributed to Nolan as Confident with method voice

#### Scenario: Caller asks for someone by name
- **WHEN** the caller says "Is Nolan there?" in the opening, Nolan has a voice profile, and no speaker matches it even weakly
- **THEN** the call is attributed to Nolan as Maybe, not Confident

#### Scenario: Transferred call with two staff
- **WHEN** both Nolan and another profiled person are strong voice matches in one call
- **THEN** the call is attributed to both people

#### Scenario: No evidence
- **WHEN** no profile has name or voice evidence for a call
- **THEN** the call is Unassigned

### Requirement: Speaker names in transcripts
When a speaker in a call is matched to a person by strong voice or by manual assignment, that speaker SHALL be shown with the person's name in the transcript. Other speakers SHALL keep their generic labels.

#### Scenario: Labeled transcript
- **WHEN** Speaker 1 is a strong voice match for Nolan
- **THEN** the transcript shows Speaker 1's segments as "Nolan"

### Requirement: Manual attribution wins
Users SHALL be able to mark a call as belonging to a person, optionally naming which speaker they are. They SHALL also be able to mark a call as not belonging to a person. Manual decisions SHALL override automatic ones and survive re-matching.

#### Scenario: Claim a missed call
- **WHEN** a user marks an Unassigned call as Nolan's and picks Speaker 2
- **THEN** the call is attributed to Nolan as Confident with method manual, and the user is offered to add Speaker 2 to Nolan's voice profile

#### Scenario: Reject a wrong match
- **WHEN** a user marks a call as not Nolan's
- **THEN** Nolan's attribution is removed from that call and is not re-added by automatic matching

#### Scenario: Confirm a Maybe
- **WHEN** a user confirms a Maybe attribution for Nolan
- **THEN** it becomes Confident with method manual

### Requirement: Re-matching when profiles change
When a profile's name variants or voice profile change, or the matching thresholds change, automatic attributions SHALL be recomputed for all transcribed calls from stored transcripts and fingerprints. No audio SHALL be re-downloaded, and manual decisions SHALL be kept.

#### Scenario: Profile enrolled after calls were transcribed
- **WHEN** Nolan's voice profile becomes usable after 100 calls were already transcribed
- **THEN** those 100 calls are re-matched and calls with Nolan's voice become attributed to him, without any Ravon requests
