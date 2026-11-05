# Tasks

## 1. Remove speaker labels

- [x] 1.1 Remove speaker separation from the pipeline (design D0): drop the segmentation model, the clustering and its threshold from the code and the image; keep the embedding model and compute a voiceprint for each line of 1 second or more (design D1); verify unit tests for the line-length rule and a `model`-marked test that a fixture call gets one voiceprint per qualifying line and no speaker labels
- [x] 1.2 Write the migration that drops `speakers` and the segment speaker column and adds the segment voiceprint column, and verify a migration test from a database created by the earlier changes' migrations, including the pre-migration backup and that existing transcript text and search still work
- [x] 1.3 Remove `speaker` and `speakers` from the transcript API and add the per-segment `has_voiceprint` flag (design D7); verify tests for the "Timestamped transcript" and "Per-line voiceprints" scenarios, and that no voiceprint ever appears in a response
- [x] 1.4 Remove speaker labels from the Call view and Copy for ChatGPT (`[m:ss] text` lines), and verify the updated component and copied-text tests for the modified "Call detail" and "Copy for ChatGPT" scenarios
- [x] 1.5 Update the compose smoke test and `docs/architecture.md` for transcripts without speakers, and verify that the `check` script passes

## 2. Data model, profiles and enrollment

- [x] 2.1 Write the migration for profiles, name variants, voice samples and attributions (design D1, with the cascade rules), and verify a migration test from the database after 1.2
- [x] 2.2 Implement profiles and name variants (create, edit, delete with cascades), and verify tests for the "People profiles" scenarios
- [x] 2.3 Implement voice samples and centroids (add or remove a call's enrolled lines, refuse lines without a voiceprint, centroid rebuild, the 3-call / 30-second usability rule), and verify tests for the "Voice enrollment from transcript lines" and "Usable voice profile" scenarios
- [x] 2.4 Implement voice presence scoring (design D3) as a pure function, and verify table-driven tests including "Too little matching speech" and calls with too little voiceprinted speech
- [x] 2.5 Add the `calibrate` command (design D9), and verify that it reads only stored data for a fixture profile and calls, makes no Ravon requests, and writes no transcript text or audio into the report

## 3. Calibration on real calls

Done after groups 4 to 6 (decided 2026-10-26). 3.1's results led to removing voice matching (design D3, group 8).

- [x] 3.1 With the user, set up the service writer's profile on the real instance and enroll lines from at least 3 calls; then run calibration on at least 10 other calls known to include him and at least 10 known not to; record the presence-score spread, choose the minimum presence, the default low and high thresholds and the usability rule, and write them with their reasoning into the change notes
- [x] 3.2 With the user, check from the same calls how often the service writer's name appears in the first 30 seconds of speech, and record the rate in the change notes

## 4. Attribution logic

- [x] 4.1 Add the voice threshold settings with provisional defaults (replaced by the calibrated ones in 3.1) and the low-below-high rule, and verify tests for the defaults and rejected values
- [x] 4.2 Implement name evidence (design D2), and verify tests for the greeting, late-name, accent and misspelling cases
- [x] 4.3 Implement the rules as a pure function (design D4), and verify table-driven tests for every scenario under "Automatic attribution rules", including the transfer and "caller asks for someone" cases
- [x] 4.4 Implement manual decisions (claim, reject, confirm Maybe), and verify tests for every scenario under "Manual attribution wins"
- [x] 4.5 Run attribution after each successful transcription, and add the de-duplicated `rematch` job type triggered by profile, sample and threshold changes (design D6); verify that a rematch over 100 stored calls makes zero Ravon requests, loads no model and leaves manual rows unchanged
- [x] 4.6 Pass name variants to the transcriber's hotword list before each job (design D8), and verify a unit test that the current variants reach the engine and a `model`-marked test that a configured name is spelled as configured

## 5. API

- [x] 5.1 Implement the admin profile and enrollment endpoints under `/api/v1/admin/profiles` (design D7), and verify tests for each, the enrollment rejection without an admin session, and the route-walk test from the core change still passing with the new admin routes
- [x] 5.2 Implement the open call-action endpoints (claim, reject, confirm), and verify tests for each without an admin session
- [x] 5.3 Add the `person`, `maybe` and `unassigned` filters and the `attributions` array to the call list; verify tests for every scenario under "Person filters on the call list" and "Person filter in the call API", and that no voiceprint or centroid ever appears in a response

## 6. Screens

- [x] 6.1 Build the People screen at `/admin/people` (design D10: list, variants, voice progress, enrolled lines by call with Remove, how calls were found, the consent note), and verify component tests including "how much more is needed"
- [x] 6.2 Add the People filter section and attribution chips to the Calls view, and verify component tests for each filter, combining with search, and Maybe markers
- [x] 6.3 Add "People on this call" with its actions to the Call view, plus the admin-only line tick boxes and "Enroll as <person>"; verify component tests for each action, that staff see no tick boxes, and that lines without a voiceprint can't be ticked
- [x] 6.4 Add the voice threshold section to the admin Settings screen, and verify component tests for editing and the low-above-high message

## 8. Remove voice matching (design D3)

Voice tasks 1.1, 1.3, 2.3 to 2.5, 3.1, 4.1, 4.3, 5.1, 6.1, 6.3 and 6.4 were built and are taken back out here.

- [x] 8.1 Remove the voiceprint step and the speaker-embedding model from the pipeline and the image; verify the pipeline tests and a `model`-marked test that a fixture call is transcribed with no voice step
- [x] 8.2 Write the migration that drops the segment `voiceprint` column, `voice_samples`, the `attributions.voice_score` column and the voice threshold settings, deletes `voice` and `name+voice` automatic rows and queues a rematch; verify a migration test from the current database, including that manual rows and transcript search are unchanged
- [x] 8.3 Remove voice samples, centroids, presence scoring, the thresholds and the `calibrate` command, and change the rules to name hit → Maybe (design D4); verify table-driven tests for every scenario under "Automatic attribution rules", and that rematch is queued only by profile and variant changes
- [x] 8.4 Remove the enrollment and sample endpoints, `has_voiceprint` and `voice_score` from the API; verify the route-walk test and that responses contain none of them
- [x] 8.5 Remove the line tick boxes and Enroll bar from the Call view, the voice progress, enrolled lines and consent note from the People screen, the voice score from "People on this call", and the Voice matching section from Settings; verify the updated component tests
- [x] 8.6 Update `docs/architecture.md` and the README for name-only attribution without voice data, and verify that the `check` script passes

## 9. Skip the recorded hold message (design D2)

Found on the working day in 7.2: both of Nolan's missed calls had his greeting after the store's recorded hold message.

- [ ] 9.1 Find recorded-message lines from the instance's own transcripts and leave them out of the 30-second opening, never skipping a line with a name variant (design D2); verify unit tests for "Greeting after the hold message", a name line that repeats across calls, and short repeated fragments, and that a rematch over the stored calls finds the two missed calls from 7.2 without adding a wrong match

## 7. End-to-end checks

- [x] 7.1 Extend the compose smoke test: the admin creates a profile; a new call with the name in the greeting becomes Maybe by name; confirming it makes it Confident; a rejected match stays rejected after a name-variant change; verify that it passes in the `check` script
- [x] 7.2 With the user, run the instance on the shop PC for one working day with the service writer's profile set up, then review his filter and the Maybe filter together, count correct, missed and wrong attributions, and record the results in the change notes

## Workflow follow-up

- Run `/opsx:verify` before archiving.
- Archive with `/opsx:archive` after `add-call-browser` has been archived.
- Then start `add-mcp-server`.
