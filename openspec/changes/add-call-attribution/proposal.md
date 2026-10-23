# Proposal

## Why

Ravon can't tell which calls belong to the service writer, because inbound calls land on the main store line. After `add-call-browser`, he can find calls by words or number, but he still sees the whole store's calls. This change works out who was on each call, by the name said in the greeting and by voice, so he can filter to his own calls and check the uncertain ones.

## What Changes

- **People profiles in a new People admin screen (`/admin/people`):** a display name, plus the name variants the transcript might contain.
- **Voice profiles:** built from calls by choosing "Speaker N is <person>" on a call screen. Voice matching starts once at least 3 calls and 60 seconds of a person's speech are enrolled. Only the admin can remove enrolled calls.
- **Automatic attribution after each transcription:** a call is matched by name evidence (a name variant in the first 30 seconds of speech) and voice evidence (similarity to a voice profile, with low and high thresholds). The result is Confident, Maybe or Unassigned, with the method and scores recorded.
- **Manual attribution:** anyone can claim a call for a person, reject a wrong match, or confirm a Maybe. Manual decisions always win over automatic ones.
- **Re-matching from stored data** whenever profiles or thresholds change. No audio is re-downloaded.
- **Calibration on real calls** before thresholds are fixed. Voice matching has to be measured on 8 kHz phone audio.
- **Name hints for the speech model:** people's name variants are passed to transcription, so names come out spelled consistently.
- **Call screens:**
  - person, Maybe and Unassigned filters on the call list
  - attribution chips on rows
  - "People on this call" (method and scores) and speaker names in the transcript and in Copy for ChatGPT
- **Voice matching thresholds** in the admin Settings screen.

## Capabilities

### New Capabilities
- `call-attribution`: people profiles, voice enrollment, name and voice evidence, the automatic attribution rules, speaker names, manual decisions and re-matching.

### Modified Capabilities
- `call-transcription`: adds "Recognize profile names reliably" (name hints from profiles).
- `instance-settings`: adds the voice-matching threshold settings.
- `admin-access`: adds the People screen to the admin area.
- `call-browser`: adds person, Maybe and Unassigned filters, attribution on rows and on the call screen, and the attribution actions.

## Impact

- **Backend:**
  - a migration for profiles, name variants, voice samples and attributions
  - an attribution module (pure functions plus a rematch job type in the existing queue)
  - admin profile endpoints, and open attribution and enrollment endpoints
  - hotword wiring into the transcriber
- **Frontend:** the People screen, filters and chips on the Calls view, and the attribution panel plus "Speaker N is …" on the Call view.
- **Data and privacy:** voice profiles of staff are biometric data. The admin should get each person's consent before enrolling them; the README and the People screen say so.
- **Depends on:** `add-call-transcription-core` and `add-call-browser`.
