# Spec Delta

## Purpose

Lets each instance define the people who use the phones and works out which of them were on each transcribed call, by name, by voice, or by hand, so a person can filter the store's calls down to their own. Attribution is per call; it never says which person spoke which line.

## ADDED Requirements

### Requirement: People profiles
The admin SHALL be able to create, edit and delete people profiles in the admin area. A profile has a display name and one or more name variants (spellings and nicknames the transcript might contain). No person-specific data SHALL be built into the application.

#### Scenario: Create a profile
- **WHEN** the admin creates a profile "Nolan" with variants "Nolan" and "Nolen"
- **THEN** the profile appears in the profile list and as a filter in the call list

#### Scenario: Delete a profile
- **WHEN** the admin deletes a profile
- **THEN** its voice profile and all its automatic attributions are deleted, and its calls revert to Unassigned unless another person is attributed

### Requirement: Voice enrollment from transcript lines
Only the admin SHALL be able to build a person's voice profile, by ticking lines on a transcribed call's screen where only that person is talking and enrolling them for that person. Only lines with a stored voiceprint SHALL be selectable. The admin SHALL be able to review and remove enrolled lines in the admin area.

#### Scenario: Enroll lines from a call
- **WHEN** the logged-in admin opens a transcribed call, ticks three of Nolan's lines and chooses "Enroll as Nolan"
- **THEN** those lines' voiceprints are added to Nolan's voice profile, and the profile shows the enrolled call count and seconds

#### Scenario: Enrollment not offered to staff
- **WHEN** someone without an admin session opens a transcribed call
- **THEN** no line tick boxes or enroll action are shown, and the enrollment endpoint rejects their request

#### Scenario: Line too short to enroll
- **WHEN** the admin views a line shorter than 1 second, or a line from a call transcribed before line voiceprints existed
- **THEN** that line can't be ticked, and the screen says why

#### Scenario: Remove enrolled lines
- **WHEN** the admin removes a call's enrolled lines from a voice profile
- **THEN** the voice profile is rebuilt without them

### Requirement: Usable voice profile
Voice matching for a person SHALL start only after enrolled lines from at least 3 calls, totaling at least 30 seconds, exist. Calibration on real calls may change these numbers.

#### Scenario: Not enough enrolled speech
- **WHEN** a profile has enrolled lines from 2 calls totaling 20 seconds of speech
- **THEN** voice matching is not used for that profile, and the profile page says how much more is needed

### Requirement: Name evidence
A profile SHALL have name evidence in a call when one of its name variants appears in the transcript within the first 30 seconds of speech. Matching SHALL tolerate small spelling differences in the transcribed name.

#### Scenario: Name in greeting
- **WHEN** a call's transcript starts "Thanks for calling Tire Pros, this is Nolan"
- **THEN** the Nolan profile has name evidence for that call

#### Scenario: Name only late in the call
- **WHEN** a profile's name appears only after the first 30 seconds of speech
- **THEN** that profile has no name evidence for the call

### Requirement: Voice presence
For each usable voice profile, the instance SHALL score how strongly the profile's voice is present anywhere in a call, from the call's stored line voiceprints, without deciding which lines that person said. A call needs a minimum number of seconds of matching speech (provisionally 4, set by calibration) before the profile counts as present. A presence score at or above the instance's high threshold is a strong voice match; a score between the low and high thresholds is a weak voice match.

#### Scenario: Strong voice match
- **WHEN** at least the minimum presence of a call's speech scores at or above the high threshold against Nolan's voice profile
- **THEN** Nolan has strong voice evidence for that call

#### Scenario: Too little matching speech
- **WHEN** only one short line of a call scores above the high threshold against Nolan's voice profile, and it adds up to less than the minimum presence
- **THEN** that line alone doesn't give Nolan strong voice evidence

### Requirement: Automatic attribution rules
After a call is Transcribed, each profile SHALL be attributed to the call as Confident or Maybe, or not at all. The rules are:
- Strong voice: Confident.
- Name with strong or weak voice: Confident.
- Name with no voice profile yet: Confident.
- Name where the voice profile has no voice match, even weak: Maybe.
- Weak voice alone: Maybe.
Each attribution SHALL record its method (name, voice, name+voice) and its scores.

#### Scenario: Name and voice agree
- **WHEN** Nolan's name is in the opening and Nolan has a weak or strong voice match in the call
- **THEN** the call is attributed to Nolan as Confident with method name+voice

#### Scenario: Outbound call without a name
- **WHEN** Nolan's name is never said but Nolan has a strong voice match in the call
- **THEN** the call is attributed to Nolan as Confident with method voice

#### Scenario: Caller asks for someone by name
- **WHEN** the caller says "Is Nolan there?" in the opening, Nolan has a voice profile, and Nolan has no voice match in the call, even weak
- **THEN** the call is attributed to Nolan as Maybe, not Confident

#### Scenario: Transferred call with two staff
- **WHEN** both Nolan and another profiled person have strong voice matches in one call
- **THEN** the call is attributed to both people

#### Scenario: No evidence
- **WHEN** no profile has name or voice evidence for a call
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
When a profile's name variants or voice profile change, or the matching thresholds change, automatic attributions SHALL be recomputed for all transcribed calls from stored transcripts and line voiceprints. No audio SHALL be re-downloaded, and manual decisions SHALL be kept.

#### Scenario: Profile enrolled after calls were transcribed
- **WHEN** Nolan's voice profile becomes usable after 100 calls with line voiceprints were already transcribed
- **THEN** those 100 calls are re-matched and calls with Nolan's voice become attributed to him, without any Ravon requests
