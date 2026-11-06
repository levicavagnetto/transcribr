# Proposal

## Why

Ravon can't tell which calls belong to the service writer, because inbound calls land on the main store line. After `add-call-browser`, he can find calls by words or number, but he still sees the whole store's calls. This change works out who was on each call from the name said in the greeting, and lets anyone confirm or correct it, so a person can filter to their own calls and check the uncertain ones.

Live testing on 2026-10-26 showed that the per-line speaker labels from `add-call-transcription-core` ("Speaker 1", "Speaker 2") are not close to correct on real 8 kHz mono calls. Attribution therefore works at the call level only: it answers "was this person on this call?", never "which lines did they say?".

Voice matching was built and measured on real calls (2026-11-05) and then dropped. The shop's service writers are all men on 8 kHz mono phone audio, and another service writer scored as high as Nolan did on his own calls. At a threshold with no wrong matches, voice found only 3 of 11 of his calls. The shop wants attribution that is hardly ever wrong, so voice is removed (design D3).

## What Changes

- **Speaker labels removed:**
  - Transcripts become plain timestamped lines, on the call screen and in Copy for ChatGPT.
  - The worker stops running speaker separation and no longer computes any voice embeddings.
  - The per-call speaker table and its fingerprints are deleted.
- **People profiles in a new People admin screen (`/admin/people`):** a display name, plus the name variants the transcript might contain.
- **Automatic attribution after each transcription, by name only:** when a name variant is heard in the first 30 seconds of speech, the call is attributed to that person as Maybe, with the name heard and its time recorded. Automatic matching never makes a call Confident.
- **Manual attribution:** anyone can claim a call for a person, reject a wrong match, or confirm a Maybe. A claimed or confirmed call is Confident. Manual decisions always win over automatic ones.
- **Re-matching from stored transcripts** whenever profiles or name variants change. No audio is re-downloaded.
- **Name hints for the speech model:** people's name variants are passed to transcription, so names come out spelled consistently.
- **Call screens:**
  - person, Maybe and Unassigned filters on the call list
  - attribution chips on rows
  - "People on this call", with the name heard and when
- **Voice matching removed:** line voiceprints, voice enrollment, voice presence scoring, the voice threshold settings and the `calibrate` command, built earlier in this change, are taken out again, with a migration that drops their data.

## Capabilities

### New Capabilities
- `call-attribution`: people profiles, name evidence, the automatic attribution rule, manual decisions and re-matching.

### Modified Capabilities
- `call-transcription`:
  - "Speaker-labeled transcript" becomes "Timestamped transcript".
  - "Per-speaker voice fingerprints" is removed.
  - adds "Recognize profile names reliably" (name hints from profiles)
- `admin-access`: adds the People screen to the admin area.
- `call-browser`:
  - "Call detail" and "Copy for ChatGPT" lose speaker labels.
  - adds person, Maybe and Unassigned filters, attribution on rows and on the call screen, and the attribution actions

## Impact

- **Backend:**
  - the speaker-separation and speaker-embedding steps and both models removed from the pipeline and the image
  - migrations that drop speakers and segment speaker labels and add profiles, name variants and attributions, then a migration that drops the line voiceprints, voice samples and voice settings added along the way
  - an attribution module (pure functions plus a rematch job type in the existing queue)
  - admin profile endpoints, and open attribution endpoints
  - hotword wiring into the transcriber
- **Frontend:**
  - speaker labels removed from the Call view and the copied text
  - the People screen, filters and chips on the Calls view
  - the attribution panel on the Call view
- **Data and privacy:** no voice data of staff or callers is kept. Profiles hold names and spellings only.
- **Depends on:** `add-call-transcription-core` and `add-call-browser`, both archived first.
