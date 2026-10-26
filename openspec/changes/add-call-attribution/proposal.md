# Proposal

## Why

Ravon can't tell which calls belong to the service writer, because inbound calls land on the main store line. After `add-call-browser`, he can find calls by words or number, but he still sees the whole store's calls. This change works out who was on each call, by the name said in the greeting and by voice, so he can filter to his own calls and check the uncertain ones.

Live testing on 2026-10-26 showed that the per-line speaker labels from `add-call-transcription-core` ("Speaker 1", "Speaker 2") are not close to correct on real 8 kHz mono calls. Attribution therefore works at the call level only: it answers "was this person on this call?", never "which lines did they say?".

## What Changes

- **Speaker labels removed:**
  - Transcripts become plain timestamped lines, on the call screen and in Copy for ChatGPT.
  - The worker stops running speaker separation.
  - The per-call speaker table and its fingerprints are deleted.
- **Per-line voiceprints:** each transcript line of 1 second or more gets a stored voiceprint, so voice matching and re-matching never need the audio again. Voiceprints never leave the instance.
- **People profiles in a new People admin screen (`/admin/people`):** a display name, plus the name variants the transcript might contain.
- **Voice profiles:**
  - The admin builds them on a call screen by ticking transcript lines where only that person talks and choosing "Enroll as <person>".
  - Voice matching starts once at least 3 calls and 30 seconds of a person's speech are enrolled. Calibration may change these numbers.
  - The admin can remove enrolled lines.
- **Automatic attribution after each transcription:** a call is matched by name evidence (a name variant in the first 30 seconds of speech) and voice presence (how many seconds of the call's lines sound like a voice profile, against low and high thresholds). The result is Confident, Maybe or Unassigned, with the method and scores recorded.
- **Manual attribution:** anyone can claim a call for a person, reject a wrong match, or confirm a Maybe. Manual decisions always win over automatic ones.
- **Re-matching from stored data** whenever profiles or thresholds change. No audio is re-downloaded.
- **Calibration on real calls** before thresholds are fixed. Voice matching has to be measured on 8 kHz phone audio.
- **Name hints for the speech model:** people's name variants are passed to transcription, so names come out spelled consistently.
- **Call screens:**
  - person, Maybe and Unassigned filters on the call list
  - attribution chips on rows
  - "People on this call", with the method and scores
  - for the admin, line ticking to enroll a voice
- **Voice matching thresholds** in the admin Settings screen.

## Capabilities

### New Capabilities
- `call-attribution`: people profiles, voice enrollment from transcript lines, name evidence and voice presence, the automatic attribution rules, manual decisions and re-matching.

### Modified Capabilities
- `call-transcription`:
  - "Speaker-labeled transcript" becomes "Timestamped transcript".
  - "Per-speaker voice fingerprints" becomes "Per-line voiceprints".
  - adds "Recognize profile names reliably" (name hints from profiles)
- `instance-settings`: adds the voice-matching threshold settings.
- `admin-access`: adds the People screen to the admin area.
- `call-browser`:
  - "Call detail" and "Copy for ChatGPT" lose speaker labels.
  - adds person, Maybe and Unassigned filters, attribution on rows and on the call screen, the attribution actions, and admin voice enrollment

## Impact

- **Backend:**
  - the speaker-separation step and its segmentation model removed from the pipeline and the image
  - a migration that drops speakers and segment speaker labels, and adds line voiceprints, profiles, name variants, voice samples and attributions
  - an attribution module (pure functions plus a rematch job type in the existing queue)
  - admin profile and enrollment endpoints, and open attribution endpoints
  - hotword wiring into the transcriber
- **Frontend:**
  - speaker labels removed from the Call view and the copied text
  - the People screen, filters and chips on the Calls view
  - the attribution panel and admin line enrollment on the Call view
- **Data and privacy:** voice profiles of staff are biometric data. The admin should get each person's consent before enrolling them; the README and the People screen say so. Line voiceprints include callers' voices; they are only ever compared with staff profiles, never named, and never returned by the API.
- **Depends on:** `add-call-transcription-core` and `add-call-browser`, both archived first.
