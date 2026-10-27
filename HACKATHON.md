# Hackathon work log

Meta Global AI Developer Hackathon — building period Oct 27 – Nov 4, 2026 (ET);
project submissions due Nov 4, 9:00 PM ET.

## Baseline (not hackathon work)

This repository starts from the public release snapshot of
[PearlLeeStudio/TheArtist](https://github.com/PearlLeeStudio/TheArtist)
(git tag `baseline`; the code matches the public commit `f043e53` of 2026-08-25).
Everything up to that tag existed before the hackathon and is **not** claimed as hackathon work:

- React 19 score editor: VexFlow staff, Tone.js + smplr playback, piano/guitar voicings,
  Roman-numeral analysis, MIDI keyboard input, per-genre comping/bass/drum playback.
- FastAPI backend serving the author's 25M-parameter Music Transformer for chord generation
  (weights on Hugging Face under `PearlLeeStudio/*`, CC BY-NC 4.0; never committed here).
- Candidate rerank: R1 Sethares roughness and R2 theory retrieval (corpora are user-supplied, not in this repo),
  rule-based song-form post-processing, voice-leading inversions, local-LLM explanations.
- Rule-based three-track arrangement behind `POST /api/generate/song` and MIDI export.
- Training and analysis pipeline under `ai/` and model-card tooling under `model/`
  (published with arXiv 2605.04998 and 2606.07334).

## Built during the hackathon

Only commits after the `baseline` tag. The demo video and the submission page show only these.

| # | Feature | Commits | Meta model / tool used | Status |
|---|---|---|---|---|
| | (rows are added as features land) | | | |
