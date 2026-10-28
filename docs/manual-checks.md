# Browser, audio and DAW checks

These checks are pending. Automated validation does not establish visual quality,
MIDI-device behavior, audible balance, PDF appearance or DAW compatibility.

Refresh the frontend, then check `/api/health` and `/api/capabilities`. Version
`1.0` with nine tools confirms the running backend includes import/export/MCP;
restart it only if unreachable or missing those routes, or after further backend
changes. Safari can exercise the score and audio workflow; use Chrome for Web MIDI.
An HTTP response establishes availability, not successful generation, audio or
DAW execution. Logic detection may succeed even while Ableton is not installed.

Follow the sections below in order: import and compare the source, revise a
passage, audition the original and alternatives, adjust the controller, save and
reopen, then inspect PDF/MIDI and the actual DAW result. Full-form planning,
Meta candidate validation/explanations and open-corpus source cards remain
unimplemented and are not part of the completed-feature checks.

## Import and revise

- [ ] Import Score is immediately left of New from Song Form. Load a chord-symbol
  PDF and compare each measure with the source preview before confirming.
  The original `backend/tests/fixtures/vector-score-c.pdf` and `vector-score-f.pdf`
  are small notes-only starter cases. The file chooser offers PDFs; image import
  remains an API capability rather than a screen option.
- [ ] Verify one-chord expansion, unknown key/meter, unsupported chord names and
  zero or three-plus symbols in a bar. A correction is required rather than silently
  discarding symbols. Cancel, close and replace files while a request is running.
- [ ] Selecting a file starts local analysis automatically with an indeterminate
  progress bar. There are no mode controls, Meta checkbox or separate review
  checkbox. Printed chords stay unchanged; chordless passages receive proposals.
  Check Printed/Inferred/Unreadable, note evidence and confidence against the
  original. Replace a file during analysis; an earlier result must not populate
  the replacement. Cancel and retry without choosing the file again.
- [ ] Import the original vector-score C/F
  fixtures without a model key: verify read pitches, bass, local source and Roman I.
  An unsupported scan reports that local reading cannot handle it, without
  suggesting a missing screen control or making an external model request.
- [ ] The footer always shows why Import reviewed score
  is disabled. Correct missing key/meter or highlighted bars using the footer
  links, then click Import reviewed score to confirm. A valid draft enables the
  button immediately. Check on a narrow mobile window as well as desktop.
  Readable C/Am key aliases normalize to C major/A minor.
- [ ] Review C, Am and G7 in C major: I, vi and V7 appear in review and after
  import. Change the review key to reanalyze fixed symbols; the main Key control
  instead transposes the song. Check Bb/Eb borrowed chords and preserve Roman
  labels in Projects, JSON backup and PDF. Source proposal metadata stays visible.
- [ ] Explicit N.C. produces an empty chord bar. Typing N.C. for an unresolved bar
  is an explicit editing choice, preserved separately from the original reading.
  A repeat-measure sign copies the immediately preceding harmony and its origin,
  including an unresolved/N.C. state; it cannot upgrade an inference to printed.
  More than two changes show all Roman numerals and require choosing the editor's
  two slots. Nothing is silently truncated.
- [ ] Explicit and inferred sections remain distinguishable. Edit labels, types and
  boundaries; reject overlaps and invalid ranges. Clicking a section label selects it.
- [ ] Drag a passage, Generate, and compare Original/A/B/C audibly with identical
  settings. Restore Original, including voicings and rests. Changes outside the
  selection survive. Replacing a score cannot apply an old in-flight result.
- [ ] Simulate a failed generation request in browser developer tools without
  stopping the server. Regular and Favorite Generate show an error, do not invent
  offline candidates and leave the score unchanged. Restore the connection and
  retry; the old error clears and real suggestions appear.
- [ ] Import/Open preserves current work in Projects. Save, refresh, Open, export
  project JSON and import it again. Chords, sections and four mixer levels survive.
  Invalid JSON and storage errors remain visible without replacing current work.

## Play and controller

- [ ] At 1366×768 and 1366×660, with panel width 300–320 px, all five panes and four
  48px mixer knobs fit. Check dark/light contrast, labels and readable values.
- [ ] First Play works in Safari. Adjust Master/Harmony/Bass/Drums while notes ring;
  each part at zero mutes independently, and Master at zero mutes everything.
  Check drag, Shift-drag, wheel, arrow keys and double-click defaults.
- [ ] Compare all 13 harmony rhythms using different first/second chords, especially
  Charleston and Half. Check slash bass, second-slot-only preview, 3/4 and 6/8 tempo,
  swing, live preset changes, pause/resume, seek, stop and loop.
- [ ] In Chrome, enable MIDI, switch to Play → Visual and keep seeing incoming notes
  without writing chords. Return to Input → MIDI for capture. Test early release,
  a changed held voicing, fewer than three held notes, device unplug/reconnect,
  panel collapse, a modal and a new song while notes are held.

## Files and DAW

- [ ] Download MIDI; import into Logic. Confirm Harmony/Bass/Drums, tempo, actual
  meter, markers, voicings, rests, swing, muted parts and no stuck notes. MIDI carries
  editable notes and GM/controller hints; DAW instrument sound may differ.
- [ ] Use Open in Logic and Ableton reveal/drag. Test a missing DAW and a backend
  error. Hosted clients must still offer MIDI download.
- [ ] Export PDF with 4/8/28/29/64 bars in light, dark and current themes. Inspect
  first cold load, all keys, slash chords, diminished/half-diminished symbols, Korean
  titles, section boundaries and page breaks. No crop, missing glyph or work date.

## Automated evidence

Frontend: 136 tests passed; TypeScript/Vite build and ESLint passed. The build still
reports the existing large-chunk warning. Backend: 282 tests passed and app import
passed. These include MIDI parsing, API errors, score-import mocks, real SDK MCP
round trips and CPU seed isolation. Frontend transport tests cover network/HTTP
failures, SSE errors, interrupted or malformed streams and real server results.
TheVoyager adapter has five mock contract tests;
its live service/complete rendering loop is not verified by those tests.

The real printed-score [review record](../experiments/meta/printed_import_review_smoke.json)
matched all eight symbols; that exact response also passes frontend review conversion
with key-relative Roman numerals. It covers one synthetic PNG, not a PDF or a
representative score collection. The direct-vision notes-only [first](../experiments/meta/note_harmony_first_attempt.json),
[second](../experiments/meta/note_harmony_second_attempt.json) and
[detail-view](../experiments/meta/note_harmony_smoke.json) trials all contain chord/pitch
errors. The ineffective detail-view runtime was removed. Those trials do not
establish direct-vision accuracy. The newer local path has independent original
vector-PDF and deterministic note-event tests; its supported encoding and unresolved
notation are described in [score analysis](score-analysis.md). Actual browser confirmation,
user-score comparison, MIDI hardware and Logic/Ableton checks remain unchecked.
