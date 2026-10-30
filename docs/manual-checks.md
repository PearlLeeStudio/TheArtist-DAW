# Browser, audio and DAW checks

Checked items below were observed in the named application. Unchecked items remain
manual coverage to complete; automated tests do not establish audible balance or
hardware compatibility.

Refresh the frontend, then check `/api/health` and `/api/capabilities`. Version
`1.0` with eleven tools confirms the running backend includes import/export/MCP;
restart it only if unreachable or missing those routes, or after further backend
changes. Safari can exercise the score and audio workflow; use Chrome for Web MIDI.
An HTTP response establishes availability, not successful generation, audio or
DAW execution. Check `meta.fullFileScoreImport` before expecting full-file import,
and `rag.sources` before expecting OMT references (`omt: ready`, `berklee: disabled`).
An inherited `THEARTIST_DISABLE_RAG=1` overrides the current OMT-on default.
Logic detection may succeed even while Ableton is not installed.

Follow the sections below in order: import and compare the source, revise a
passage, audition the original and alternatives, adjust the controller, save and
reopen, then inspect PDF/MIDI and the actual DAW result. Full-form planning and
candidate review are implemented. Generation can attach OMT source excerpts with
author/editor credit and license links; their browser checks below remain open.

## Observed workflow

- [x] Safari: Muse Spark Full form produced a 16-bar song with five sections,
  applied it and closed the dialog. No execution log appeared above the staff.
- [x] Safari: section selection and real F1 passage generation returned Original
  and three alternatives. Cmd+A selected all 32 chord slots; title-field Cmd+A
  retained text selection. Section labels and chords survived a reload/remount.
- [x] Safari: saved project displayed only four bars and offered the complete
  Export menu at the right. Its Light PDF contained all 16 bars on one page,
  with title, Roman numerals, slash chords and five section labels, inspected in Preview.
- [x] Safari: light/dark Play, piano/guitar drawing and Rhythm/controller views
  rendered. First Play changed to Pause and advanced the playhead; the Harmony
  fader changed to 50 and double-click restored 100. This is visual/control evidence,
  not a listening or keyboard-fader pass.
- [x] Safari: the self-authored 20-bar C–F–C fixture imported with three inferred
  sections (8/8/4), preserved note evidence and whole-score Meta explanations.
- [x] Logic: Open in Logic produced three editable MIDI regions from bars 1–17,
  80 BPM, 4/4, C major and Intro/Verse/Pre-Chorus/Chorus/Outro markers. This does
  not establish DAW sound equivalence, controller interpretation or Scripter execution.
- [x] Safari: Enable MIDI explicitly reported unsupported Web MIDI.
  Chrome with an actual MIDI device remains untested.

Screenshots: [Projects export](../screenshot/08-projects-export.png),
[Logic handoff](../screenshot/09-logic-handoff.png),
[PDF](../screenshot/10-pdf-export.png),
[Import](../screenshot/11-import-context.png). Actual model evaluation and its
failures are recorded in [evaluation.md](evaluation.md).

## Import and revise

- [ ] Import Score is immediately left of New from Song Form. Load a chord-symbol
  PDF and compare each measure with the source preview before confirming.
  The original `backend/tests/fixtures/vector-score-c.pdf` and `vector-score-f.pdf`
  are small notes-only starter cases. Local and Meta assist accept PDFs;
  the explicit Meta only reader also accepts PNG/JPEG/WebP when available.
- [ ] Verify one-chord expansion, unknown key/meter, unsupported chord names and
  zero or three-plus symbols in a bar. Unknown key/meter still requires correction;
  unfinished chord reading can open in the score view. Missing/unsupported slots
  stay unassigned with the source preserved. Longer bars retain all source symbols
  for placement rather than silently selecting two. Cancel, close and replace files
  while a request is running.
- [x] Safari desktop: Reader can be selected before a file. Selecting the original
  vector-score-c.pdf fixture only prepares its preview; changing Reader retains the
  file without analyzing. **Analyze score** with TheArtist only completes the local
  review. Changing Reader then clears the review and disables import until analysis
  is requested again. A PNG can be selected with TheArtist only, reports the required
  Reader when Analyze is clicked, and stays selected when switching to Meta only.
  No Meta analysis was submitted in these checks.
- [ ] An explicitly started analysis shows an indeterminate progress bar.
  The default **TheArtist + Meta** reader sends complete
  score context to at most two eight-bar harmony calls and one form call. Confident
  local inferences are eligible; printed chords stay unchanged. The status reports
  reviewed coverage, while request IDs remain in provenance. Switching readers
  during analysis cancels the old request and waits for **Analyze score**; verify
  its late response cannot populate the review. TheArtist only makes no Meta call; Meta only
  is explicit and unavailable on the public host. Failures stay visible.
  The Review score dialog has no chord-analysis list. After import, select a bar
  to check its chords, Roman numerals and retained source against the original.
  Replace a file during analysis; an earlier result must not populate
  the replacement. Cancel and retry without choosing the file again.
- [ ] Import the original vector-score C/F
  fixtures without a model key: verify read pitches, bass, local source and Roman I.
  An unsupported scan reports that local reading cannot handle it without making
  an implicit external model request; Meta only is a separate choice.
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

## Theory references

- [ ] With OMT ready and Berklee disabled in capabilities, generate a passage and
  expand Theory references. Check that each excerpt has its actual source link,
  authors/editors, license link, copyright and modification notice; follow both
  links. These are retrieved passages, not a generated explanation of the song.
- [ ] With retrieval disabled or the corpus unavailable, generate again: no stale
  notes or Theory progress phase should appear. Existing user servers must not be
  stopped to perform this check; use a separate configured test server.
- [ ] Inspect the cards in light/dark themes and a narrow window. Compare actual
  relevance to the selected transition, separately from whether the UI renders.

## Projects

- [ ] Each card shows only its first staff row, without a Preview score toggle.
  Export at the right of Delete offers MIDI, PDF, Logic, Ableton and Scripter like
  the score editor. With another song open, verify the file contains the selected
  saved project's entire score, title, instruments, mutes and mixer settings.

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
  stay disabled until it does), choose target bars, Outro and contrast and run
  **Muse Spark**. The dialog stays open while generating and applies a successful
  result before closing. The staff shows section labels without the execution band.
- [ ] Reopen Full form → **Run details** for trace and Undo. Undo restores the exact
  score; Export trace downloads JSON without keys. A changed sketch or settings
  prevent an obsolete plan from being applied.
- [ ] Ctrl+A / ⌘A selects every editor bar. In a title input or dialog it retains
  native text selection. Projects does not intercept the shortcut.
- [ ] Force a failure using an isolated test server or browser request blocking:
  the dialog
  shows the error and keeps the staff untouched. With the backend available,
  **Genre template** still works without a Meta call.
- [ ] Cancel an in-progress plan. The current bounded request may finish, but no
  subsequent section or Meta request starts; already incurred cost stays recorded.
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

Three review passes covered implementation, independent failure-path inspection
and verification after the fixes:

1. The first full pass completed 476 backend and 212 frontend tests, frontend
   build and lint.
2. Independent review found an unstarted SSE worker retaining a plan reservation
   and the Set Chord field retaining the previous selection. The fixes are
   [`fd2b5d8`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/fd2b5d8) and
   [`bc0f817`](https://github.com/PearlLeeStudio/TheArtist-DAW/commit/bc0f817),
   with focused regressions for both.
3. The final full pass completed **479 backend tests** and the app import check,
   plus **215 frontend tests**, lint and build. The build retains the existing
   large-chunk warning. Safari reproduced the corrected Set Chord flow by
   selecting C in bar 1, F in bar 9 and applying F to the selected bar.
   Documentation contracts, local links, image references and public-file contents
   were also inspected; this does not establish untested audio or hardware behavior.

The [observed workflow](#observed-workflow) records what Safari, Preview and Logic
actually displayed. Remaining unchecked scenarios above retain their narrower
scope: listening, MIDI hardware, GM/controller behavior, Scripter execution,
additional layouts and edge cases. The
[evaluation](evaluation.md) separately records real Meta request results,
including failed PNG reading and the planner's unresolved judge decisions.
