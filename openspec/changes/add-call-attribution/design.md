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
- On real calls (2026-11-05), voice matching against an enrolled profile could not tell the shop's service writers apart (D3).
- Staff usually answer with their name ("Tire Pros Stillwater, this is Nolan"). Callers sometimes ask for someone by name.
- Some calls are transferred between staff.

Mockups (People, and attribution on the Calls and Call screens): see `docs/architecture.md`. They predate D0 and D3 and still show speaker labels and voice; the screens follow this design instead.

## Goals / Non-Goals

**Goals:**
- Attribution answers "was this person on this call?" and nothing finer.
- Automatic attribution is hardly ever wrong about who handled a call. Anything it isn't sure of is a Maybe for a person to confirm.
- Attribution can be recomputed from stored transcripts at any time, without touching Ravon.
- Manual decisions are never overwritten.

**Non-Goals:**
- Saying which person spoke which line, on screen, in the API or in copied text.
- Identifying anyone by voice. No voice data is kept.
- Per-person logins, or hiding other people's calls. Visibility stays open, as decided.
- Live, in-call identification.

## Decisions

### D0. Speaker labels removed
- The pipeline stops running speaker separation. The pyannote segmentation model, the clustering and its 0.43 threshold all go, and the segmentation model leaves the image.
- Segments lose their `speaker` column. The transcript API loses the per-segment `speaker` and the `speakers` list.
- The Call view shows `m:ss` and the text per line. Copy for ChatGPT writes one `[m:ss] text` line per segment.

### D1. Data model
- **Segments:** no `speaker` and no `voiceprint` column.
- **`speakers`:** dropped, with its fingerprints.
- **`profiles`:** ID, display name, created time.
- **`name_variants`:** profile, variant, with a unique (profile, normalized variant).
- **`attributions`:** one row per (call, profile), with:
  - status: `confident`, `maybe` or `rejected`
  - source: `auto` or `manual`
  - method: `name` or `manual`
  - the name hit (variant and time)
- **Deleting a profile** cascades to its variants and all its attributions, manual ones included, since the person no longer exists.

### D2. Name evidence
- Take the words whose start time falls in the first 30 seconds of speech, measured from the first word, not from the start of the recording.
- Normalize them: lowercase, strip punctuation, fold accents.
- Fuzzy-match each normalized variant against word n-grams of the same length with `rapidfuzz` `fuzz.ratio` ≥ 88.
- **Why only the opening:** it's where staff say their name, and later mentions ("ask Nolan") are usually about someone, not by them.

### D3. Voice matching removed
Voice matching was built in this change (line voiceprints from the WeSpeaker ResNet34 embedding model, enrollment from ticked lines, a presence score against low and high thresholds, and a `calibrate` command) and measured on the real instance. It is removed.
- **Before centering:** every line voiceprint shared one large phone-channel component (the mean of all voiceprints had length 0.91). Every call scored 0.85 to 0.98 against Nolan, so voice matched almost every call.
- **After centering on the instance mean** (2026-11-05, Nolan enrolled from 3 calls, best 2 s of each call): 11 calls with Nolan scored 0.53 to 0.82; 32 calls without him, almost all answered by other service writers, scored -0.49 to 0.78.
  - Call 26578631, confirmed not Nolan, scored 0.78. Only 3 of Nolan's 11 calls scored higher.
  - With no wrong matches, voice found 3 of 11 of his calls. At 0.60 / 0.70 it found 10 of 11 but matched 2 of 32 calls wrongly, one of them as Confident.
- **Why it fails here:** the shop's service writers are all men, on 8 kHz mono phone audio, and a transcript line often holds both the service writer and the customer. Similar adult male voices are the hardest case for this kind of model, and centering can't fix the other two.
- **What goes:** the embedding model in the image, the voiceprint step in the pipeline, the segment `voiceprint` column, `voice_samples`, the voice threshold settings, presence scoring, `transcribr calibrate`, the enrollment endpoints and UI, and the voice parts of the People screen.
- **Revisit only if** recordings with the service writer and the customer on separate channels become available. That would be a new change.

### D4. Rules
Implemented exactly as the `call-attribution` "Automatic attribution rules" requirement, as a pure function: `(name hits, manual rows) → attribution rows`.
- A name hit gives a `maybe`, `auto` row with method `name` and the variant and time heard. Automatic rows are never `confident`.
- **Why Maybe:** the name alone can't tell "this is Nolan" from "is Nolan there?". Confirm or Not <person> takes one click on the call screen and settles it for good.
- A profile with a manual row keeps it untouched. A `rejected` manual row blocks any automatic row for that profile on that call.

### D5. Enrollment
Removed with voice matching (D3).

### D6. When attribution runs
- After each successful transcription, the job runner calls the rules for that call, in the same transaction that marks it Transcribed.
- A `rematch` job type (scope: all calls) runs when a profile is created or deleted, or its name variants change.
- A rematch only deletes and rewrites `source=auto` rows. It reads stored transcripts, so it makes no Ravon requests and needs no models.
- Rematch jobs are de-duplicated: a pending job absorbs new requests.

### D7. Endpoints
- **Admin, under `/api/v1/admin/profiles`:** profile CRUD and name variants.
- **Open, call actions:**
  - `POST /api/v1/calls/{id}/attributions` to claim for a person.
  - `DELETE /api/v1/calls/{id}/attributions/{profile}`, which stores a `rejected` manual row.
  - `POST …/confirm` to confirm a Maybe.
- **The call list from `add-call-browser` gains** `person`, `maybe` and `unassigned` filters, and an `attributions` array per row.
- **Open, people for the filters:** `GET /api/v1/people` gives each person's ID, display name and call counts, plus the Maybe and Unassigned counts. It holds names and numbers only, so staff can build the People filter without the admin endpoints.
- **Filter meanings:** `person` is that person's Confident and Maybe calls; with `maybe` it narrows to their Maybes. `unassigned` is Transcribed calls with no Confident or Maybe attribution, and can't be combined with the other two. Call detail and each list row carry an `attributions` array; rejections are not shown.
- **Removed:** the enrollment and sample endpoints, the per-segment `has_voiceprint` flag, and `voice_score` in attributions.

### D8. Hotwords
- Before each transcription, the job runner passes the current set of name variants to the transcriber's hotword list, which the core change built and left empty.
- If there are no profiles, the list stays empty.

### D9. Calibration
Removed with voice matching. The measurements that led to removing it are in D3.

**Name in the opening (task 3.2, 2026-11-05, Nolan, variant "Nolan"):**
- Of 16 calls confirmed by hand as Nolan's, his name was found in the first 30 seconds of speech in 11 (69%), at 2.9 to 6.1 s.
- **Missed (5):**
  - 26578634: the store's recorded greeting runs past 30 s, so his own greeting falls outside the window.
  - 26578064 and 26577818: the caller speaks first and no greeting was transcribed.
  - 26577754: the speech model heard "Nolan" as "no one".
  - 26579023: he answered a call asking for someone else, without saying his name.
- **Wrong (2 of 9 rejected calls):** 26579201 ("Thanks, Nolan… this is Parker") and 26579369 ("working with Zach and then Nolan"). Both were answered by Parker. Maybe status and Not <person> handle these.
- **So:** a name hit was right 11 of 13 times (85%). That is why automatic matches stay Maybe. About a third of his calls need Add a person.
- **Possible follow-ups, not in this change:** measuring the window from the end of the recorded greeting; profiles for Parker and Zach, so their calls are found too.

**Working day (task 7.2, 2026-11-05, 1:29 PM to 4:38 PM, no manual decisions made beforehand):**
- 15 calls were transcribed. The user confirmed who answered each; 3 couldn't be placed from the transcript (26579746, 26579896, 26580126) and are left out.
- **Nolan's calls (4):** 2 were found as Maybe by name (26580141, 26580174). 2 were missed (26579885, 26580164): the caller sat through the store's recorded hold message, and he greeted them at 72 s and 78 s, after the 30-second window.
- **Other people's calls (8, answered by Miles, Gibson, Parker and Zach):** no wrong matches.
- **So:** no wrong matches on the day; misses come from the recorded hold message pushing the greeting late. Measuring the window from the end of the recorded message is the most useful next improvement (a follow-up change).

### D10. UI
- **People screen (`/admin/people`):**
  - the list of people, with name-variant chips, Edit and Delete
  - a breakdown of "how calls were found" (by name, by hand, still Maybe)
- **Calls view:**
  - a People section in the filter panel: each person, Maybe and Unassigned, with counts
  - attribution chips on rows. Maybe chips are dashed, using the theme's attribution tokens.
- **Call view:**
  - "People on this call", with the method and evidence (the name heard and its time), and Not <person>, Confirm and Add a person
  - the transcript stays plain timestamped lines, with no names and no tick boxes
- **Settings:** no voice matching section.

## Risks / Trade-offs

- **Names can be misheard or not said at all, especially on outbound calls.** → Hotwords and fuzzy matching help; calls with no name are Unassigned, and Add a person claims them.
- **Every automatic match needs a click to become Confident.** → It's one click on the call screen or from the Maybe filter, and it's what keeps automatic attribution from being wrong. Task 3.2 and the day of use in 7.2 show how many clicks that is in practice.
- **A caller naming someone gives that person a Maybe.** → Not <person> removes it for good.

## Migration Plan

- The earlier migrations in this change dropped `speakers` and the segment speaker column, and added the segment voiceprint column, `voice_samples`, profiles, name variants and attributions.
- **A new migration** drops the segment `voiceprint` column, the `voice_samples` table, the `voice_score` column of `attributions` and the two voice threshold settings. Existing `voice` and `name+voice` automatic rows are deleted and a rematch is queued, so every call is re-attributed by name. Manual rows keep their status and stay `manual`. The migration runner takes a pre-migration backup.
- **Rollback:** start the previous image and restore the pre-migration backup.

## Open Questions

- None open. Whether names in the opening are said often enough to make the person filter useful is measured in task 3.2 and the working day in 7.2.
