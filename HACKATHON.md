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
| 1 | **New from Song Form**: a dialog picks one of 17 song-form sections and a chord count; the section is placed after the last used measure, generated and applied (A/B/C kept for swapping); section labels on the staff; an automatic title until the user edits it; drag-select Generate names its section explicitly instead of guessing from position | [`21379ec`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/21379ec) | none yet (the Muse Spark planner fills sections later) | done |
| 2 | **Section generation API**: `POST /api/generate/section` and `/stream`, 17 song-form rules, key anchoring for fresh sections, every requested bar generated, one SSE helper | [`baedd71`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/baedd71) [`c303805`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/c303805) [`1e14334`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/1e14334) | none | done |
| 3 | **Meta Model API client**: OpenAI-compatible client for Muse Spark (Standard) and Meta open weights, worst-case cost reservation, spend cap, persistent ledger with request ids | [`ead3b96`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/ead3b96) | Muse Spark 1.3: first strict-JSON song-form plan ([record](experiments/meta/llm_smoke_d1.json), request `7ee8ff92`) | done; product use lands with the planner |
| 4 | **Speed probe** with the D1 measurements ([before](experiments/speed/d1_before_full_length.md) / [after](experiments/speed/d1_after_full_length.md) full-length generation) | [`1328625`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/1328625) | none | done |
| 5 | **Fixes**: brand-yellow accent token; editor state survives a reload (`?reset=1` clears it); slash chords voiced with the named bass at the bottom (F/C = C F A) | [`5621888`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/5621888) [`730a6bd`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/730a6bd) [`dc1415e`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/dc1415e) | none | done |
| 6 | **Play panel**: Play mode is one Teenage Engineering style device panel that never scrolls — transport, BPM and drum-level knobs, and four panes: Visual (keyboard or fretboard; playback voices chords the same way), Instrument (31 harmony sounds by family), Rhythm (13 named comping rhythms on a 16-step LED row; bass on/off, and the bass now plays in the editor) and Drums (Auto, Off or 15 patterns with a K/S/H step grid). A change is heard on the next strike without stopping; swing patterns swing every layer; the picks survive genre changes and reloads and are saved with a session, so MyPage replays it as the editor played it | [`c27cfdf`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/c27cfdf) [`1fd7f22`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/1fd7f22) | none | built; browser check pending |
| 7 | **Song API play options**: `POST /api/generate/song` takes the Play panel's `harmony_rhythm`, `drum_pattern` (an id or `"off"`) and `harmony_instrument`, mirrored from the editor's tables and kept in step by a node-run parity test; the render fits the model's bars to the requested length and no longer overlaps same-pitch MIDI notes | [`f9f5bb8`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/f9f5bb8) | none | done |
