# Design

## Context

See `proposal.md` for the motivation and `specs/` for the required behavior. This change builds on two earlier changes.
- **`add-call-transcription-core` already stores:**
  - transcripts as time-stamped segments (lines) with word timestamps
  - per-line speaker labels and one fingerprint per speaker label per call, from sherpa-onnx speaker diarization; this change removes both (D0)
  - a job queue with a type column
  - a settings registry, and an admin area that's ready for another screen
- **`add-call-browser` provides:** the call list, call detail, and Copy for ChatGPT.

Facts from the v1 prototype and live testing that matter here:
- The audio is 8 kHz mono, with both sides of the call in one channel, so the sides can't be separated by channel.
- On real calls (2026-10-26), the diarization's speaker labels were not close to correct. Its clustering threshold had been tuned on one real call.
- Staff usually answer with their name ("Tire Pros Stillwater, this is Nolan").
- Some calls are transferred between staff.

Mockups (People, and attribution on the Calls and Call screens): see `docs/architecture.md`. They predate D0 and still show speaker labels; the screens follow this design instead.

## Goals / Non-Goals

**Goals:**
- Attribution answers "was this person on this call?" and nothing finer.
- Attribution can be recomputed from stored data at any time, so thresholds and profiles can be tuned after the fact without touching Ravon.
- Manual decisions are never overwritten.
- Thresholds come from measurements on real calls, not guesses.

**Non-Goals:**
- Saying which person spoke which line, on screen, in the API or in copied text.
- Per-person logins, or hiding other people's calls. Visibility stays open, as decided.
- Identifying customers by voice. Only staff profiles exist, and callers' voiceprints are only ever compared, never named.
- Live, in-call identification.

## Decisions

### D0. Speaker labels removed
- The pipeline stops running speaker separation. The pyannote segmentation model, the clustering and its 0.43 threshold all go, and the segmentation model leaves the image.
- The speaker-embedding model (WeSpeaker ResNet34, ONNX, through sherpa-onnx) stays, to compute the line voiceprints (D1).
- Segments lose their `speaker` column. The transcript API loses the per-segment `speaker` and the `speakers` list.
- The Call view shows `m:ss` and the text per line. Copy for ChatGPT writes one `[m:ss] text` line per segment.
- Calls transcribed before this change keep their text but have no line voiceprints. Name evidence and manual decisions work on them; voice presence does not (see Open Questions).

### D1. Data model (the next migration)
- **Segments:** drop `speaker`, and add `voiceprint` (nullable BLOB).
  - The voiceprint is the L2-normalized float32 embedding of the line's audio.
  - It's set for lines of 1 second or more. Shorter lines get none, since their embeddings are unreliable.
- **`speakers`:** dropped, with its fingerprints.
- **`profiles`:** ID, display name, created time.
- **`name_variants`:** profile, variant, with a unique (profile, normalized variant).
- **`voice_samples`:** profile, call, segment index, added time, unique per (profile, call, segment). It references the segment's stored voiceprint, so it needs no copy.
- **`attributions`:** one row per (call, profile), with:
  - status: `confident`, `maybe` or `rejected`
  - source: `auto` or `manual`
  - method: `name`, `voice`, `name+voice` or `manual`
  - the name hit (variant and time)
  - the voice presence score (D3)
- **Deleting a profile** cascades to its variants, samples and `auto` attributions. Manual rows for that profile are deleted too, since the person no longer exists.
- **Size:** a 256-value float32 voiceprint is 1 KB, so a 5-minute call takes about 60 KB.

### D2. Name evidence
- Take the words whose start time falls in the first 30 seconds of speech, measured from the first word, not from the start of the recording.
- Normalize them: lowercase, strip punctuation, fold accents.
- Fuzzy-match each normalized variant against word n-grams of the same length with `rapidfuzz` `fuzz.ratio` ≥ 88.
- **Why only the opening:** it's where staff say their name, and later mentions ("ask Nolan") are usually about someone, not by them.

### D3. Voice presence
- **Centering:** every stored voiceprint shares one large component from the phone channel and codec. On live data the mean of all line voiceprints had length 0.91, every call scored 0.85 to 0.98 against an enrolled person, and voice matched almost every call. So before any comparison, each voiceprint has the **instance mean** subtracted and is renormalized to unit length.
  - The instance mean is the duration-weighted mean of every stored line voiceprint. It's computed when matching or calibration starts and never stored.
  - Lines transcribed later shift it slightly; calls keep their scores until the next rematch, which any enrollment or threshold change queues.
  - Centering moved scores on live data to roughly -0.55 to 0.83, so the thresholds were recalibrated (D9).
- **Profile centroid:** the L2-normalized, duration-weighted mean of its enrolled lines' centered voiceprints. It's computed from the current samples whenever it's needed and never stored, so it can't fall out of step with them (for example when a re-transcribed call takes its enrolled lines with it).
- **When a profile is usable:** enrolled lines from 3 or more distinct calls, totaling 30 or more seconds. Calibration (D9) kept both.
- **Line score:** the cosine similarity between a line's centered voiceprint and a usable centroid.
- **Presence score** of a call for a profile:
  - It's the highest score `s` at which the call's lines scoring `s` or more add up to at least the **minimum presence**.
  - The minimum presence is 2 seconds, set by calibration (D9).
  - A call with less voiceprinted speech than that has no presence score.
- **Bands:** a presence score at or above the high threshold is strong; at or above low but below high is weak.
- Line scores are working values only; they are never stored per line or shown.

### D4. Rules
Implemented exactly as the `call-attribution` "Automatic attribution rules" requirement, as a pure function: `(name hits, presence scores, usable profiles, thresholds, manual rows) → attribution rows`.
- A profile with a manual row keeps it untouched.
- A `rejected` manual row blocks any automatic row for that profile on that call.
- When a profile has a usable voice but the call has too little voiceprinted speech for a presence score (a very short call, or one transcribed before line voiceprints), the voice can't tell either way. A name hit then counts as "name with no voice profile yet" (Confident), not as "no voice match" (Maybe).

### D5. Enrollment
- Only the admin enrolls. On a Transcribed call, the logged-in admin sees a tick box per line, ticks lines where only that person talks, and chooses "Enroll as <person>".
- Lines without a voiceprint can't be ticked, and say why. That covers lines under 1 second and lines from calls transcribed before this change.
- Enrolling adds `voice_samples` rows, which changes the centroid, and queues a rematch for that profile. Removing samples on the People screen does the same.

### D6. When attribution runs
- After each successful transcription, the job runner calls the rules for that call, in the same transaction that marks it Transcribed.
- A `rematch` job type (scope: all calls, or one profile) runs when:
  - name variants change
  - samples are added or removed
  - thresholds change
  - a profile is deleted
- A rematch only deletes and rewrites `source=auto` rows. It reads stored text and voiceprints, so it makes no Ravon requests and needs no models.
- Rematch jobs are de-duplicated: a pending "all" job absorbs new requests.

### D7. Endpoints
- **Admin, under `/api/v1/admin/profiles`:**
  - profile CRUD and name variants
  - listing enrolled samples, by call, with line times and seconds
  - adding samples (`{call_id, lines: [idx…]}`) and removing them
- **Open, call actions:**
  - `POST /api/v1/calls/{id}/attributions` to claim for a person.
  - `DELETE /api/v1/calls/{id}/attributions/{profile}`, which stores a `rejected` manual row.
  - `POST …/confirm` to confirm a Maybe.
- **The call list from `add-call-browser` gains** `person`, `maybe` and `unassigned` filters, and an `attributions` array per row.
- **Open, people for the filters:** `GET /api/v1/people` gives each person's ID, display name and call counts, plus the Maybe and Unassigned counts. It holds names and numbers only, so staff can build the People filter without the admin endpoints.
- **Filter meanings:** `person` is that person's Confident and Maybe calls; with `maybe` it narrows to their Maybes. `unassigned` is Transcribed calls with no Confident or Maybe attribution, and can't be combined with the other two. Call detail and each list row carry an `attributions` array; rejections are not shown.
- **The transcript gains** a per-segment `has_voiceprint` flag, so the admin's enrollment tick boxes know which lines qualify.
- **Voice data stays inside:** scores are returned as numbers, and voiceprints and centroids never.

### D8. Hotwords
- Before each transcription, the job runner passes the current set of name variants to the transcriber's hotword list, which the core change built and left empty.
- If there are no profiles, the list stays empty.

### D9. Calibration
- **The command:** once the service writer's profile is enrolled on the real instance, `transcribr calibrate --profile <id> --calls <ids…>` reads the stored voiceprints of the chosen calls and writes a local report. For each call it gives:
  - the seconds of speech with a voiceprint
  - the best line score
  - the presence score at minimum presence values of 2, 4, 6 and 8 seconds
- It makes no Ravon requests. The report contains no audio and no transcript text.
- **Scoring with the user:** at least 10 calls known to include the service writer and 10 known not to include him are scored. None of the "him" calls may have been used for enrollment.
- **Choosing the defaults** from the two groups' presence scores:
  - **minimum presence:** the value that separates the groups best
  - **low:** just above the highest "not him" presence score
  - **high:** where 95% or more of "him" presence scores sit above
- The usability rule (3 calls, 30 seconds) is checked against the same data.
- The chosen numbers and their reasoning go in the change notes, and become the defaults.

**Results (2026-11-05, profile Nolan, enrolled from 3 calls, centered scoring):**
- Labelled calls from 2026-11-04 16:00 to 2026-11-05 13:15: 11 with Nolan (added by hand), 32 without (6 rejected by hand, 26 with no Nolan chip, checked by the user). The enrolled call 26578963 was left out.
- Presence at 2 s separated the groups best. Nolan: 0.53 to 0.82, 10 of 11 at 0.61 or more. Not Nolan: -0.49 to 0.60, except 26578631 (0.78, confirmed not Nolan) and 26579023 (0.69). Longer minimums lowered Nolan's short calls more than the others (26577789 drops to 0.17 at 8 s).
- **Chosen:** minimum presence 2 s, low 0.60 (just above the main not-Nolan group), high 0.70. On these calls: 7 of 11 Nolan calls strong, 3 weak (Maybe), 1 missed (26577754, 0.53); 30 of 32 others untouched, one false strong and one false Maybe.
- **Usability rule kept** at 3 calls and 30 s: the 3-call profile already gives this spread. A bad enrollment (26569647, which scored 0.15 against the rest) dragged the profile down, so the People screen's Remove matters.
- Voice alone stays a backstop: manual Not <person> is how the false strong match is fixed.

### D10. UI
- **People screen (`/admin/people`):**
  - the list of people, with name-variant chips
  - voice profile progress ("2 of 3 calls, 20 of 30 s")
  - enrolled lines grouped by call, with Remove
  - a breakdown of "how calls were found"
  - the consent note
- **Calls view:**
  - a People section in the filter panel: each person, Maybe and Unassigned, with counts
  - attribution chips on rows. Maybe chips are dashed, using the theme's attribution tokens.
- **Call view:**
  - "People on this call", with the method and evidence (the name heard and its time, the voice presence score), and Not <person>, Confirm and Add a person
  - for the logged-in admin only: tick boxes on transcript lines and "Enroll as <person>"
  - the transcript stays plain timestamped lines, with no names

## Risks / Trade-offs

- **Voice matching may be weak on 8 kHz mono phone audio.** → Calibrate first, before the rules are finalized. Name matching works without voice, the Maybe status and manual decisions absorb errors, and thresholds can be retuned with a rematch.
- **A line can hold both voices** when the speech model doesn't break at a turn. → Presence needs several seconds of matching lines, not one, and enrollment uses lines the admin picked as one voice only.
- **Names can be misheard or not said at all, especially on outbound calls.** → Hotwords and fuzzy matching, voice presence, and manual claims as the backstop.
- **A wrong enrollment pollutes a voice profile.** → Only the admin enrolls, and the People screen lists every enrolled line with Remove, which triggers a rematch.
- **Voice profiles are biometric data, and line voiceprints include callers.** → Voiceprints never leave the instance and are never returned by the API. Callers are never named. Deleting a profile deletes its samples. The People screen and the README tell the admin to get each person's consent before enrolling them.
- **Line voiceprints grow the database** (about 60 KB per 5-minute call). → That's a few hundred MB at thousands of calls, within the deployment's disk allowance.
- **Rematching all calls gets slower as history grows.** → Each call is dot products over its stored line voiceprints plus a text scan, so at this volume (thousands of calls) it takes seconds to a minute. A rematch for one profile only touches that profile's rows.

## Migration Plan

- The next migration drops `speakers` and the segment speaker column, and adds the segment voiceprint column and the four tables. The core change's migration runner takes a pre-migration backup.
- After deployment there are no profiles, so every call is Unassigned until the admin adds people.
- **Rollback:** start the previous image and restore the pre-migration backup, which loses only the profiles, attributions and voiceprints created since.

## Open Questions

- **Should calls transcribed before this change get line voiceprints?** That needs a backfill job that fetches their audio from Ravon again (read-only, like Listen). Left out for now; decide after the shop has used voice matching on new calls.
- **Should the attribution panel show voice scores to everyone,** or only to the admin? The spec shows them on the call screen, and calibration may suggest hiding them if they confuse people. This doesn't change the data or the API.
