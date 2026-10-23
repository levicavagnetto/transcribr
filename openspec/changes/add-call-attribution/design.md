# Design

## Context

See `proposal.md` for the motivation and `specs/` for the required behavior. This change builds on two earlier changes.
- **`add-call-transcription-core` already stores:**
  - transcripts with word timestamps
  - one row per speaker label per call, with an L2-normalized float32 fingerprint (the mean speaker embedding from sherpa-onnx) and its speech seconds
  - a job queue with a type column
  - a settings registry, and an admin area that's ready for another screen
- **`add-call-browser` provides:** the call list, call detail, and Copy for ChatGPT.

Facts from the v1 prototype that matter here:
- The audio is 8 kHz mono, with both sides of the call in one channel.
- Staff usually answer with their name ("Tire Pros Stillwater, this is Nolan").
- Some calls are transferred between staff.

Mockups (People, and attribution on the Calls and Call screens): see `docs/architecture.md`.

## Goals / Non-Goals

**Goals:**
- Attribution can be recomputed from stored data at any time, so thresholds and profiles can be tuned after the fact without touching Ravon.
- Manual decisions are never overwritten.
- Thresholds come from measurements on real calls, not guesses.

**Non-Goals:**
- Per-person logins, or hiding other people's calls. Visibility stays open, as decided.
- Identifying customers by voice. Only staff profiles exist, and caller fingerprints are only ever compared, never named.
- Live, in-call identification.

## Decisions

### D1. Data model (the next migration)
- **`profiles`:** ID, display name, created time.
- **`name_variants`:** profile, variant, with a unique (profile, normalized variant).
- **`voice_samples`:** profile, call, speaker label, added time, unique per (profile, call, speaker). It references the core change's `speakers` row, so it reuses that stored fingerprint and needs no copy.
- **`attributions`:** one row per (call, profile), with:
  - status: `confident`, `maybe` or `rejected`
  - source: `auto` or `manual`
  - method: `name`, `voice`, `name+voice` or `manual`
  - the name hit (variant and time)
  - the best voice score and the matched speaker label
- Deleting a profile cascades to its variants, samples and `auto` attributions. Manual rows for that profile are deleted too, since the person no longer exists.

### D2. Name evidence
- Take the words whose start time falls in the first 30 seconds of speech, measured from the first word, not from the start of the recording.
- Normalize them: lowercase, strip punctuation, fold accents.
- Fuzzy-match each normalized variant against word n-grams of the same length with `rapidfuzz` `fuzz.ratio` ≥ 88.
- **Why only the opening:** it's where staff say their name, and later mentions ("ask Nolan") are usually about someone, not by them.

### D3. Voice evidence
- **Profile centroid:** the L2-normalized mean of its enrolled samples' fingerprints. It's recomputed whenever samples change.
- **When a profile is usable:** 3 or more distinct calls and 60 or more seconds of enrolled speech.
- **Score:** the cosine similarity between each speaker in the call (one with a fingerprint) and each usable centroid.
- **Bands:** a score at or above the high threshold is strong; at or above low but below high is weak.

### D4. Rules
Implemented exactly as the `call-attribution` "Automatic attribution rules" requirement, as a pure function: `(name hits, voice scores, usable profiles, thresholds, manual rows) → attribution rows`.
- A profile with a manual row keeps it untouched.
- A `rejected` manual row blocks any automatic row for that profile on that call.

### D5. Speaker naming
- A speaker label gets a person's name when either:
  - a manual "Speaker N is …" decision names it, or
  - it is that profile's strong voice match, and no other profile is also strongly matched to the same label.
- The transcript API returns a `person` field per segment, which the Call view and Copy for ChatGPT use.

### D6. When attribution runs
- After each successful transcription, the job runner calls the rules for that call, in the same transaction that marks it Transcribed.
- A `rematch` job type (scope: all calls, or one profile) runs when:
  - name variants change
  - samples are added or removed
  - thresholds change
  - a profile is deleted
- A rematch only deletes and rewrites `source=auto` rows. It reads stored text and vectors, so it makes no Ravon requests and needs no models.
- Rematch jobs are de-duplicated: a pending "all" job absorbs new requests.

### D7. Endpoints
- **Admin, under `/api/v1/admin/profiles`:** profile CRUD, name variants, listing enrolled samples, and removing a sample.
- **Open, call actions:**
  - `PUT /api/v1/calls/{id}/speakers/{label}` with `{person}` or `{caller: true}` for "Speaker N is …". Naming a person adds a voice sample. Naming the caller removes any sample of that label.
  - `POST /api/v1/calls/{id}/attributions` to claim for a person, optionally with a speaker.
  - `DELETE /api/v1/calls/{id}/attributions/{profile}`, which stores a `rejected` manual row.
  - `POST …/confirm` to confirm a Maybe.
- **The call list from `add-call-browser` gains** `person`, `maybe` and `unassigned` filters, and an `attributions` array per row.
- **Voice data stays inside:** scores are returned as numbers, and fingerprints and centroids never.

### D8. Hotwords
- Before each transcription, the job runner passes the current set of name variants to the transcriber's hotword list, which the core change built and left empty.
- If there are no profiles, the list stays empty.

### D9. Calibration
- A `realsite` command, `transcribr calibrate --calls <ids…>`, processes user-chosen recordings and writes a local report:
  - the speakers and their speech seconds per call
  - the pairwise cosine similarities between speakers across calls
- The report contains no audio and no transcript text.
- With the user, at least 10 calls known to include the service writer and 10 known not to include him are scored. The defaults go between the two groups' distributions:
  - **low:** just above the highest "not him" score
  - **high:** where 95% or more of "him" scores sit above
- The chosen numbers and their reasoning go in the change notes, and become the setting defaults.

### D10. UI
- **People screen (`/admin/people`):**
  - the list of people, with name-variant chips
  - voice profile progress ("2 of 3 calls, 40 of 60 s")
  - enrolled samples with Remove
  - a breakdown of "how calls were found"
  - the consent note
- **Calls view:** a People section in the filter panel (each person, Maybe, Unassigned, with counts), and attribution chips on rows. Maybe chips are dashed, using the theme's attribution tokens.
- **Call view:**
  - "People on this call", with the method and evidence, and Not <person>, Confirm and Add a person
  - "Speakers", with "Speaker N is …"
  - person names in the transcript

## Risks / Trade-offs

- **Voice matching may be weak on 8 kHz mono phone audio.** → Calibrate first (task group 1), before the rules and UI are finalized. Name matching works without voice, the Maybe status and manual decisions absorb errors, and thresholds can be retuned with a rematch.
- **Names can be misheard or not said at all, especially on outbound calls.** → Hotwords and fuzzy matching, voice evidence, and manual claims as the backstop.
- **A wrong "Speaker N is …" from anyone on the shop network pollutes a voice profile.** → The user chose open access. The admin sees every enrolled sample on the People screen and can remove it, which triggers a rematch.
- **Voice profiles are biometric data.** → They are derived from stored fingerprints that never leave the instance and are never returned by the API, and deleting a profile deletes its samples. The People screen and the README tell the admin to get each person's consent before enrolling them.
- **Rematching all calls gets slower as history grows.** → It's cheap per call (a few vector dot products and a text scan). At this volume (thousands of calls) it takes seconds. A rematch for one profile only touches that profile's rows.

## Migration Plan

- The next migration adds the four tables. The core change's migration runner takes a pre-migration backup.
- After deployment there are no profiles, so every call is Unassigned until the admin adds people.
- **Rollback:** start the previous image and restore the pre-migration backup, which loses only the profiles and attributions created since.

## Open Questions

- **Should the attribution panel show raw voice scores to everyone,** or only to the admin? The spec shows them on the call screen, and calibration may suggest hiding them if they confuse people. This doesn't change the data or the API.
