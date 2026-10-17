# Demo video kit

Everything on screen is the live app at `http://localhost:8000` (plus the real GitHub PR page). Every number in a
caption or the narration is read from the page while recording.

## 1. Record your voice

Open `video/out/VOICEOVER.md`. It has one block per scene with the exact lines, the scene's start time and
length, and the file name to save.

- Phone or laptop mic is fine. Use a quiet room, about 15 cm from the mic, and the same spot for every clip.
- **One file per scene:** `video/voice/scene_01.m4a` … `scene_12.m4a` (`.wav` and `.mp3` also work).
- Retake freely: only the file on disk counts. A clip that runs longer than its scene is fine, because the
  scene is stretched to fit. A missing clip leaves that scene silent.

## 2. Assemble

```bash
python video/assemble.py --voice video/voice/
```

This cleans the audio (high-pass, denoise, −16 LUFS), places each clip at its scene, and stretches any scene
whose clip is longer. It writes `video/out/chainbreaker_demo_final.mp4`, `chainbreaker_demo_final.srt` and
`youtube_description_final.txt` (chapters for the stretched timeline).

## 3. Re-record the whole video

The run opens and merges real PRs in the demo org, so always start from a fresh demo:

```bash
.venv/bin/cb reset-demo && .venv/bin/cb crawl --dataset demo && .venv/bin/cb load --dataset demo
```

The app must run in public mode (CNCF names pseudonymized):

```bash
PUBLIC_MODE=1 .venv/bin/uvicorn chainbreaker.api:app --port 8000
```

Then:

```bash
python video/preflight.py && python video/record.py && python video/post.py
```

`preflight.py` checks the app, datasets, redaction, the eval numbers and a two-question agent chat, then resets
the demo. Run `cb reset-demo` again afterwards so judges see the compromised starting state.

Outputs (all gitignored) land in `video/out/`: `chainbreaker_demo_silent.mp4`, `VOICEOVER.md`,
`chainbreaker_demo.srt`, `youtube_description.txt`, `chainbreaker_30s_silent.mp4` and `frames/scene_XX.png`.
Scene text and minimum holds live in `video/scenes.json`.
