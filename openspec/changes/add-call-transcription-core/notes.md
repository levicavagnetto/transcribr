# Change notes: add-call-transcription-core

Results from steps that run against the real Ravon site, as the tasks ask. Counts only; no
caller numbers or call content.

## 3.7 `transcribr ravon-check` against admin.ravon.net (2026-10-22)

- **Login:** works with the plain form POST through the allow list.
- **Queues:** Ravon lists 9 queues: `tireProz-hudsales` (Hudson Sales/CS x700), `tireProz-salescustserv` (Stillwater Sales/CS x600), `tireProz-accounting` (x500), `tireProz-AndysQueue` (x550), `tireProz-Hudson_AfterHOURS` (x701), `tireProz-internetsales` (x400), `tireProz-salesqone` (x200), `tireProz-salesqtwo` (x300), `tireProz-SWafterHRS` (x599).
- **Parser check against a known day:** `tireProz-salescustserv` on 2026-10-09 returned **79 calls**, the same count v1 measured for that day. That confirms the DataTable parsing on the real page.
- **2026-10-21:** 128 calls in total (Hudson 76, Stillwater 52, the other queues 0).
- **Search speed:** each one-day search took 1.1–1.7 s.
- **Finding:** the user's first run hit a one-off `ReadTimeout` on the first search, beyond the 20-second limit, and the check stopped without counting any queue. A rerun showed no queue is consistently slow. Two changes followed:
  1. The client now allows 10 s to connect and 60 s for Ravon to answer. Persistent slowness still trips the 5-failure backoff.
  2. `ravon-check` reports each queue's failure and carries on, exiting 1 if any queue failed.
- **Tooling note:** on Windows, uv 0.13's `--env-file` drops backslashes from the path (`..\.env` becomes `...env`). Use forward slashes: `uv run --env-file ../.env transcribr ravon-check`.

## 5.3-5.4 Pipeline on the synthetic two-voice clip (2026-10-22)

The clip is two Windows TTS voices acting out a 37-second shop call, encoded like Ravon's audio.

- **Speed:** `small.en` int8 on the dev laptop transcribed it in about 3 s.
- **Names without hints:** the transcript said "Tire Pro's" and "Silver Rado".
- **Names with hints:** with hotwords `Tire Pros, Silverado, Nolan`, both came out exactly. Name hints are planned for `add-call-attribution`. A shop vocabulary list (store name, vehicle models, brands) may be worth adding there too.
- **Speaker separation:** sherpa-onnx's clustering threshold separates the two voices correctly at 0.3-0.4. At 0.45 it merges them, and at 0.2 it splits them into 4. The provisional default is 0.35. This is synthetic speech, so recheck it on real calls in `add-call-attribution`'s calibration.
- **Fingerprint similarity per turn** (WeSpeaker ResNet34): same voice 0.85-0.94, different voices 0.60-0.69. That's a useful first reference for the voice thresholds.
