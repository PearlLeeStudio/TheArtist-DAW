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
  zero or three-plus symbols in a bar. Unknown key/meter still requires correction;
  unfinished chord reading can open in the score view. Missing/unsupported slots
  stay unassigned with the source preserved. Longer bars retain all source symbols
  for placement rather than silently selecting two. Cancel, close and replace files
  while a request is running.
- [ ] Selecting a file starts the analysis automatically with an indeterminate
  progress bar. The **Meta assist** box is checked by default when the server has
  Meta enabled and a key: the status names the bars Muse Spark interpreted and the
  request ids, or says Meta was not called because local reading resolved every
  bar. Unchecking (or checking) it with a file loaded analyzes again; with Meta off
  on the server the box is disabled with a notice. Printed chords stay unchanged;
  chordless passages receive proposals.
  The Review score dialog has no chord-analysis list. After import, select a bar
  to check its chords, Roman numerals and retained source against the original.
  Replace a file during analysis; an earlier result must not populate
  the replacement. Cancel and retry without choosing the file again.
- [ ] Import the original vector-score C/F
  fixtures without a model key: verify read pitches, bass, local source and Roman I.
  An unsupported scan reports that local reading cannot handle it, without
  suggesting a missing screen control or making an external model request.
- [ ] The footer always shows why Import reviewed score
  is disabled. Correct missing key/meter or highlighted project fields using the footer
  links, then click Import reviewed score to confirm. Valid project metadata enables the
  button immediately. Check on a narrow mobile window as well as desktop.
  Readable C/Am key aliases normalize to C major/A minor.
- [ ] Review C, Am and G7 in C major: I, vi and V7 appear in the score view after
  import. Change the review key to reanalyze fixed symbols; the main Key control
  instead transposes the song. Check Bb/Eb borrowed chords and preserve Roman
  labels in Projects and PDF. Source proposal metadata stays visible.
- [ ] Explicit source N.C. produces an empty chord bar labeled N.C. Unresolved
  slots are labeled Unresolved instead. Existing saved user-chosen N.C. metadata
  remains separate from the original reading.
  A repeat-measure sign copies the immediately preceding harmony and its origin,
  including an unresolved/N.C. state; it cannot upgrade an inference to printed.
  More than two changes retain all original symbols in the selected bar's source
  and require placing the editor's two slots there. Nothing is silently truncated.
- [ ] Explicit and inferred sections remain distinguishable. Edit labels, types and
  boundaries; reject overlaps and invalid ranges. Clicking a section label selects it.
- [ ] Drag a passage, Generate, and compare Original/A/B/C audibly with identical
  settings. Restore Original, including voicings and rests. Changes outside the
  selection survive. Replacing a score cannot apply an old in-flight result.
- [ ] Simulate a failed generation request in browser developer tools without
  stopping the server. Regular and Favorite Generate show an error, do not invent
  offline candidates and leave the score unchanged. Restore the connection and
  retry; the old error clears and real suggestions appear.

## Projects

- [ ] Importing a score or editing another project preserves current work in
  Projects. Save, refresh and choose the card's Edit action to return to the
  editor. Chords, sections, Roman labels, source evidence and mixer levels survive.
  Storage errors remain visible without replacing current work. Project-file
  download and import controls are absent.
- [ ] Select individual project checkboxes, then Select all; every card can be
  selected and the all-selected state follows individual changes. Delete selected
  asks for confirmation of the selection. Cancel keeps the list, selection and
  playback unchanged. Confirm removes only the selected projects, including all
  projects when Select all was used; retained projects survive refresh.
- [ ] Simulate a storage failure before confirming Delete selected. The error
  stays visible, the full project list and selection remain available, and playback
  is unchanged. Restore storage and retry successfully.
- [ ] Deleting the saved project currently playing stops its playback. Deleting
  other selected projects lets the unselected playing project continue.

## Play and controller

- [ ] At 1366×768 and 1366×660, with panel width 300–320 px, the active chord and
  compact 🎹/🎸 selector remain below transport on every Play tab. Confirm its
  accessible labels and tooltips still say Piano/Guitar in English. The piano
  keeps its natural SVG proportions with compact surrounding space. Switch only
  the drawing and confirm the sound does not change. Check the bright Apple-style
  silver hardware panel in the light theme and near-black panel, fader bays and
  keys with light labels in the dark theme, with no green cast. Keep the upper
  housing black and selected faces warm amber in both themes. At viewport
  heights of at least 900 px, check that the
  responsive panel fits without an outer vertical scrollbar. Shorter windows
  retain an outer scrolling fallback. Instrument, Rhythm and Drums each fit their
  available area without internal scrolling; the bottom faders stay in place when
  changing tabs.
- [ ] The header theme emoji is 8 px inside the unchanged 32×28 px button area.
  Confirm its accessible label and pointer/keyboard operation remain available.
- [ ] Piano and guitar drawings use a black background in both app themes. Check
  note labels, muted text and guitar fret labels remain readable against it.
  The black housing continues from the playback keys and CD through the chord,
  drawing and selector surroundings to Rhythm/Drums, with no silver separators in
  the margins or gaps. Its top corners are rounded, including the space above the
  playback keys; subtle inset grooves distinguish the black keys without an
  outlined frame.
- [ ] All six black transport keys stay in one row beside the 27 px 💿 disc. The
  main Play key is about 1.65 times the width of the neighboring keys. The disc
  rotates only while actual playback runs, pauses at its current angle and respects
  reduced-motion preferences. Play uses a system Futura-first stack when installed,
  falling back to Avenir Next and then sans-serif.
- [ ] Instrument exposes Auto and emoji family selectors for keyboard, guitar,
  strings, woodwind and brass. The current family shows 4–8 readable sound buttons
  without scrolling. Its family selectors and sound grid both use five columns;
  the sound buttons stay 36 px tall, matching the family keys even when a family
  has only one row. Extra pane height stays empty; reach all 31 sounds with pointer and keyboard and verify the
  selected highlight and saved sound.
- [ ] Below the keyboard/guitar drawing, Rhythm and Drums each have a full-width
  black status window 60 px tall. Names such as Bossa and Samba use 12 px regular
  text at the right, like the Piano label. Step cells are flat black/green, without
  raised bevels or shadows. Rhythm HARM/BASS
  and drum K/S/H steps remain visible when any selection tab is open. Tabs sit
  below both windows. Muted rows remain distinguishable.
- [ ] Each pane starts with a full-width On/Off button and a separate full-width
  Auto choice. Instrument controls harmony mute, Rhythm controls Bass on/off, and
  Drums restores its previous Auto/manual pattern when switched back on. Muting
  harmony restores the prior audible level without changing the chosen instrument.
  Check mute, change tabs, unmute and reload, and check that loading a different
  project does not restore the previous project's instrument or pattern.
- [ ] Rhythm and drum presets use four-column text radio buttons with wrapped
  labels and fill the remaining height. Exactly one preset or Auto is selected
  while enabled; Off is the top button state. Arrow/Home/End includes Auto and
  presets without moving the On/Off button. No extra status windows appear inside
  the selection tabs.
- [ ] Selection buttons, tab keys and the small emoji selector have unlit faces
  when unselected and a warm amber illuminated face when selected. Each uses a
  recessed face with a dark upper groove and soft lower highlight, without a
  decorative outline ring. Hover feedback ends when the pointer leaves.
  Check pointer and keyboard selection, one selected preset per group, and Bass
  off's unlit face and explicit off label. The separate status LEDs remain flat
  green without shadows.
- [ ] First Play works in Safari. Adjust Master/Harmony/Bass/Drums while notes ring;
  each part at zero mutes independently, and Master at zero mutes everything.
  Bottom controls have no tab. BPM and all four volume controls are vertical faders
  with photo-inspired slim black tracks and 10 px round metal caps. Names sit below,
  with no visible numbers, percent values or scales. Check that the full range-input
  area remains usable for dragging despite the small visible cap. Check pointer/touch
  drag, Up/Down, Home/End
  and double-click defaults. Saving and reopening retains the actual levels.
  BPM spans 20–300 in steps of one and resets to 80 on double-click.
- [ ] Compare all 13 harmony rhythms using different first/second chords, especially
  Charleston and Half. Check slash bass, second-slot-only preview, 3/4 and 6/8 tempo,
  swing, live preset changes, pause/resume, seek, stop and loop.
- [ ] In Chrome, enable MIDI, switch to Play and keep seeing incoming notes above every tab
  without writing chords. Return to Input → MIDI for capture. Test early release,
  a changed held voicing, fewer than three held notes, device unplug/reconnect,
  panel collapse, a modal and a new song while notes are held.

## New from Song Form

- [ ] The dialog's title matches its button. Key, Genre and Model at the top are
  pickers shared with the song settings above the staff and Input → Generate: a
  new key transposes the score, a genre switches to the model it is served by, a
  model sets its genre, and the controls above the staff show the same values.
- [ ] **Section**: pick a part (Intro, Verse, Chorus …) and its length in **Bars**
  (1–64; the hint shows the chords, two per bar); "Placed at bars …" follows the
  last bar with chords. Generate writes it there.

## Complete the form

- [ ] New from Song Form → **Full form**: with an empty score pick a Genre first
  (in the dialog or above the staff; a fresh score has none and both run buttons
  stay disabled until it does), choose target bars, Outro and contrast and run **Plan a new song**; with a
  sketch run **Complete the form**. The band above the staff shows the chips in order (plan → validate →
  revise → each section → judge), each with latency, $ and request id.
- [ ] Nothing changes on the staff until **Apply**; **Undo** restores the exact
  score; **Export trace** downloads JSON without keys.
- [ ] Force a failure (stop the backend, or `THEARTIST_META_ENABLED=0`): a red chip,
  the spend so far, the staff untouched, and the **Genre default form (own model
  only)** button still works and is labelled as rules.
- [ ] Sections rewritten by the song-form rules (first chord, final cadence) carry
  the "cadence: rules" note, never an AI label.

## Files and DAW

- [ ] Download MIDI; import into Logic. Confirm Harmony/Bass/Drums, tempo, actual
  meter, markers, voicings, rests, swing, muted parts and no stuck notes. MIDI carries
  editable notes and GM/controller hints; DAW instrument sound may differ.
- [ ] Use Open in Logic and Ableton reveal/drag. Test a missing DAW and a backend
  error. Hosted clients must still offer MIDI download.
- [ ] Export → **Logic Scripter script**: in Logic, MIDI FX ▸ Scripter ▸ Open Script
  in Editor, paste, Run Script. Play the **Whole form** from bar 1 and check it stops
  at the form's last bar; pick one **Section**, set **Start bar** and **Loop**, and
  check only that section repeats; cycle a region; stop mid-chord (no stuck notes);
  check 3/4 or 6/8 timing against the MIDI export and switch **Beat unit** if it
  drifts; Transpose and the Harmony/Bass switches; incoming keyboard notes pass
  through. See
  [plugin/logic-scripter/README.md](../plugin/logic-scripter/README.md).
- [ ] Export PDF with 4/8/28/29/64 bars in light, dark and current themes. Inspect
  first cold load, all keys, slash chords, diminished/half-diminished symbols, Korean
  titles, section boundaries and page breaks. No crop, missing glyph or work date.

## Automated evidence

Frontend: 140 tests passed; TypeScript/Vite build and ESLint passed. The build still
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
