# Tasks

## 1. Calibration on real calls

- [ ] 1.1 Add the `realsite` calibration command (design D9) that processes user-chosen recording IDs and writes speakers, speech seconds and pairwise fingerprint similarities to a local report, with no audio and no transcript text in it; verify it runs on two fixture calls through the fake Ravon
- [ ] 1.2 With the user, run calibration on at least 10 calls known to include the service writer and at least 10 known not to; record the similarity spread, choose the default low and high thresholds, and write them with their reasoning into the change notes
- [ ] 1.3 With the user, check from the same calls how often the service writer's name appears in the first 30 seconds of speech, and record the rate in the change notes

## 2. Data model and profiles

- [ ] 2.1 Write the next migration (profiles, name variants, voice samples, attributions; design D1, with the cascade rules), and verify a migration test from a database created by the core change's migrations, including the pre-migration backup
- [ ] 2.2 Implement profiles and name variants (create, edit, delete with cascades), and verify tests for the "People profiles" scenarios
- [ ] 2.3 Implement voice samples and centroids (add or remove a call's speaker, centroid rebuild, the 3-call / 60-second usability rule), and verify tests for the "Voice enrollment from existing calls" scenarios
- [ ] 2.4 Add the voice threshold settings with the calibrated defaults and the low-below-high rule, and verify tests for the defaults and rejected values

## 3. Attribution logic

- [ ] 3.1 Implement name evidence (design D2), and verify tests for the greeting, late-name, accent and misspelling cases
- [ ] 3.2 Implement voice evidence and the rules as pure functions (design D3–D4), and verify table-driven tests for every scenario under "Automatic attribution rules", including the transfer and "caller asks for someone" cases
- [ ] 3.3 Implement speaker naming (design D5), and verify tests for strong-voice, manual and conflicting-match cases
- [ ] 3.4 Implement manual decisions (claim with an optional speaker, reject, confirm Maybe, "Speaker N is …" adding or removing a sample), and verify tests for every scenario under "Manual attribution wins"
- [ ] 3.5 Run attribution after each successful transcription, and add the de-duplicated `rematch` job type triggered by profile, sample and threshold changes (design D6); verify that a rematch over 100 stored calls makes zero Ravon requests, loads no model and leaves manual rows unchanged
- [ ] 3.6 Pass name variants to the transcriber's hotword list before each job (design D8), and verify a unit test that the current variants reach the engine and a `model`-marked test that a configured name is spelled as configured

## 4. API

- [ ] 4.1 Implement the admin profile endpoints under `/api/v1/admin/profiles` (design D7), and verify tests for each, plus the route-walk test from the core change still passing with the new admin routes
- [ ] 4.2 Implement the open call-action endpoints (speakers, claim, reject, confirm), and verify tests for each without an admin session
- [ ] 4.3 Add the `person`, `maybe` and `unassigned` filters and the `attributions` array to the call list, plus a `person` field per transcript segment; verify tests for every scenario under "Person filters on the call list" and "Person filter in the call API", and that no fingerprint or centroid ever appears in a response

## 5. Screens

- [ ] 5.1 Build the People screen at `/admin/people` (design D10: list, variants, voice progress, enrolled samples with Remove, how calls were found, the consent note), and verify component tests including "how much more is needed"
- [ ] 5.2 Add the People filter section and attribution chips to the Calls view, and verify component tests for each filter, combining with search, and Maybe markers
- [ ] 5.3 Add "People on this call", "Speakers" with "Speaker N is …", and person names in the transcript to the Call view; verify component tests for each action
- [ ] 5.4 Use person names in Copy for ChatGPT, and verify the copied-text tests from `add-call-browser` with a matched speaker
- [ ] 5.5 Add the voice threshold section to the admin Settings screen, and verify component tests for editing and the low-above-high message

## 6. End-to-end checks

- [ ] 6.1 Extend the compose smoke test: the admin creates a profile; a new call with the name in the greeting is attributed by name; enrolling speakers from three calls makes voice matching usable and a later call is attributed by voice; a rejected match stays rejected after a threshold change; verify that it passes in the `check` script
- [ ] 6.2 With the user, run the instance on the shop PC for one working day with the service writer's profile set up, then review his filter and the Maybe filter together, count correct, missed and wrong attributions, and record the results and any threshold changes in the change notes

## Workflow follow-up

- Run `/opsx:verify` before archiving.
- Archive with `/opsx:archive` after `add-call-browser` has been archived.
- Then start `add-mcp-server`.
