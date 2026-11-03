# Editor reference

What each control in the arrangement workspace does and where its limits are.
The [workflow guide](arrangement-workflow.md) walks the same tools in order;
the [README](../README.md#what-the-editor-does) keeps the one-line summary.

**Import Score → review chords and song form → select a passage → Original/A/B/C
→ arrange in Play → export MIDI or PDF.** Local code reads supported vector-score
notation and proposes note-based harmony; the author's Music Transformer generates
chord variations and bounded contextual suggestions for sparse read-note passages.
Fixed following chords now affect candidate ranking as well as preceding harmony.
With **Use Meta model**, a readable PDF opens locally first and its original-file
Meta check runs in the background; if Meta fails, the local harmony stays and the
failure is reported. Bar counts, key, meter, chords and transient note evidence are compared.
Differences remain review flags; model agreement is not proof
of correctness. If local reading is unsupported, the result clearly states that
local cross-checking was unavailable. The unchecked path never calls Meta.
The musician corrects the import, chooses the passage and keeps the version they want.

## Controls

- **Import Score**, immediately left of **New from Song Form**, accepts one
  PDF or image up to 8 MiB. Choose the file and optionally check **Use Meta model**,
  then click **Analyze and import**. File selection and checkbox changes do not start analysis;
  changing the checkbox during analysis cancels that request. The score opens on the
  staff as soon as it is read: printed chords are preserved, only passages without
  chords receive note-based harmony proposals, and bars to check carry a **Review**
  or **Unresolved** mark with their reading/review status. Inferred chords are
  interpretations, not verified original harmony; melody notes and their durations
  are not imported. Unresolved or unsupported chords stay editable without blocking
  import; their original chord symbols are retained, while extracted notes and
  source-evidence text are discarded after processing. Only an unusable title,
  key, meter, tempo or section range stops in the dialog for correction, with
  **Import reviewed score** to confirm; the footer explains the blocker.
  The checkbox is off by default. Every import sends the selected file to the app
  server for analysis; checking it also sends the full original to Meta. The app
  keeps no uploaded-score or decoded-score cache. A truncated, timed-out or invalid
  Meta response leaves the local reading available; unresolved bars remain editable.
  Meta supports up to 128 written bars. A larger or failed Meta reading can still
  open all locally readable bars (up to 512), labeled as local recovery.
  Unequal bar counts retain the complete local reading instead of merging misaligned
  bars. Printed local chords and N.C. are preserved. Images and unsupported PDFs
  require the checkbox; their Meta result states when no local comparison was possible.
  Local note reading stays distinct from own-model harmonization suggestions.
  API defaults remain local; the separate `auto` and `meta` API modes remain supported.
- **Roman-numeral analysis** follows the review key: in C major, C → I, Am → vi,
  G7 → V7. Changing the review key reanalyzes the same symbols. The editor's main Key
  control retains its existing behavior of transposing the score. Source proposals
  remain available after importing, saving and reopening a project.

- **Sections** preserves explicit versus inferred labels, lets you edit boundaries,
  and selects a region by its staff label. **Original/A/B/C** changes only the chosen
  slots and can restore the exact original voicings.
- **Reharmonize** develops existing harmony while considering the chords before
  and after the selected passage. **Change up to** offers 1, 2, 3 or 4 changed
  chords per alternative; this is a maximum, so a candidate may change fewer.
  Meta compares bounded searches scored by the selected Music Transformer and
  returns three choices. **Origin / Alter 1 / Alter 2 / Alter 3** share one row.
  Select alternatives together; overlapping choices replace each other. **Apply**
  keeps the preview and closes the cards (Ctrl/⌘+Z undoes it); **×** discards
  changes since the last Apply.
  Empty slots stay unchanged; use Generate to create a new passage.
- **Second ear** under a three-candidate list asks the judge model which candidate
  fits, on facts code computed (chords outside the key, changed slots, repetition of
  the previous section, roughness). Each reason shows its fact marked *analyzer
  confirmed* or *model statement*, plus the request id and cost; picking a version
  stays your click.
- **Projects** saves work in this browser. **Edit** returns a saved project to the
  editor; loading another score first preserves the current work. Select individual
  projects or **Select all**, then **Delete selected** after confirmation. There is
  no account or cloud synchronization. Cards show the first staff row and offer the
  same **Export** menu as the editor, using the saved project's complete score and
  playback settings even when another song is open.
- **New from Song Form → Full form** defaults to **Muse Spark only**: Meta plans
  the form and writes every new chord, preserving the existing sketch. The entire
  result must have the planned section lengths and playable chord symbols before
  it can be applied. **Music Transformer + Meta review** keeps the hybrid path;
  **Genre template** uses the Music Transformer without a Meta call.
  For a fresh arrangement, choose **Start a new song**: the existing score is
  saved in Projects before the new song starts, with key, genre, tempo and meter
  carried over. After Undo, the dialog selects an available target length.
  A successful run is applied from the dialog; the staff stays free of execution
  logs. Reopen the dialog's collapsed **Run details** for Undo and the trace.
  Ctrl+A or ⌘A selects every bar in the editor; text inputs retain native selection.
  Drag across the staff to select slots, then Ctrl/⌘+X, C and V cut, copy and paste
  them: a copied passage that divides the selection repeats over it, anything else
  is written forward from the first selected slot and adds bars as needed. Delete
  clears the selection and Ctrl/⌘+Z undoes cut, paste and clear. The clipboard
  holds the chords with their voicings and the plain text `Dm7 G7 | Cmaj7 | -`,
  which can also be pasted from elsewhere. Right-click offers the same edits.
  In the hybrid/template path, the chord model receives key, meter, genre and preceding chords. Section identities
  are not learned conditioning tokens in the served tokenizer: Muse or the genre
  template plans the form, and song-form rules adjust starts, loops and cadences.
  Meta-only chords are not replaced by these rules; the trace names Muse Spark
  as their source and records both planning and composition calls.
  The [three-seed paired evaluation](../experiments/agent_eval/fixed-seed/comparison.md)
  completed 60/60 pairs with actual F1 generation. Muse increased section-type
  variety and reduced out-of-key slots in the diatonic subset, but 21/60 final
  judgments still requested regeneration. This does not establish a listening preference.
- **Play** shows the active chord on a piano or guitar, with 31 instrument sounds,
  13 harmony rhythms and 15 drum patterns. Harmony, Bass and Drums have independent
  mute controls; BPM, Master and the three part levels remain visible as faders.
  Auto follows genre defaults, and explicit sound/rhythm choices override it.
  The mix and playback settings are saved with each project. After the first Play
  gesture, family browsing and sound hover/focus preload samples; a first uncached
  sound can still take time to download. See [measured performance](../experiments/speed/runtime-performance.md)
  for generation/import improvements and the limits of the audio checks.
- **Export** downloads editable, three-part MIDI with tempo, meter, section markers
  and mixer levels, or an A4 score PDF. On the local backend, Logic opens the MIDI
  and Ableton reveals it in Finder; on the hosted site the same actions go through the
  [local Mac bridge](midi-input.md#open-a-hosted-score-in-logic-pro), and
  Download MIDI works everywhere without it.
- **Logic Scripter script**: the same arrangement as a Logic Pro Scripter MIDI FX
  script that plays the harmony and bass inside Logic, following its transport,
  locate and cycle ([plugin/logic-scripter](../plugin/logic-scripter/README.md)).
- The same service is available through [REST and MCP](mcp.md). TheVoyager has
  a thin MCP adapter; a native AU/VST3 plugin is a future separate client.

## Feature overview

| | |
|---|---|
| **Arrange on a staff** | Import or enter harmonic material, edit section boundaries, select measures or slot ranges, and preserve slash chords |
| **Compare harmonic alternatives** | Combine Reharmonize choices with a 1–4 change limit per alternative, preview Origin and Apply; Generate keeps its Original/A/B/C comparison |
| **Develop a complete form** | Add sections or extend a sketch with Meta-only, hybrid or genre-template generation; preserve the current project before starting fresh |
| **Choose the harmonic engine** | F1–F5, F1 v2, Phase 0 and 11 genre LoRAs serve a 13-genre vocabulary. Model training, the F1 checkpoint-selection caveat and evaluation limits are documented under [AI Model](models.md#ai-model) |
| **Live progress streaming** | `/api/generate/stream` SSE pipeline shows each phase (Read → Load → Compose → Rank → Voice → Done) as the model thinks; a Theory phase retrieves attributed source excerpts when an enabled corpus is ready; OMT is enabled by default after its setup step |
| **Candidate ranking** | R1 — Sethares sensory roughness, plus local OMT text relevance when its corpus is ready. Berklee is disabled by default. Retrieval relevance is not a musical-quality score. |
| **Voice-leading inversions** | Post-process injects slash-chord inversions (e.g. `Am7/C`) where they smooth the bass line — the LM only emits root-position chords, voice leading is added on top |
| **MIDI input with confirm flow** | Hold a chord ≥3 s → auto-commit · release early → Confirm card with root-cycling chips, slash-chord inversion detection, and a 3-chord transition view (prev → curr → next + voice-leading arrows) |
| **Audio playback** | Tone.js + smplr — sampled piano, GM guitars / keys / strings, and 15 drum pattern presets. Switch instruments live mid-playback. |
| **Controller mixer** | Always at the bottom of Play: separate BPM, Master, Harmony, Bass and Drums faders. Live output gains are saved with each session; the lowest volume position mutes the part, Master mutes the whole mix. |
| **Editable DAW delivery** | Three-part MIDI carries tempo, meter, section markers and levels; score PDF and Logic Scripter exports provide additional handoff formats |
| **Dark + light theme** | Classical staff with an editorial dark/light palette; a tactile Play panel with compact text keys, flat status cells and slim vertical faders. |
| **Resizable right panel** | Drag the boundary 300–640 px wide; collapse with a short tab-aligned toggle. |
| **Generation provenance** | Backend fallback results are explicitly labeled `rules`; transport failures stay errors. Model results retain `source: ai`, `modelUsed`, and the slots changed by song-form rules. |
| **Returning choruses** | Full form offers **Keep the theme** or **New progression**. A same-length chorus can reuse the first complete progression with cadence-only changes; the trace identifies the source and exact changed slots. [OMT-on local timing and limits](../experiments/speed/chorus-memory.md). |
