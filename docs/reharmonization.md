# Reharmonize an arrangement in context

Reharmonize is the harmonic-revision step in the
[arrangement workflow](arrangement-workflow.md). Keep the source passage,
compare substitutions against neighboring harmony, then audition the result
with the arrangement's existing sounds, rhythms and mix.

Drag-select existing chords in the score, right-click the passage, and choose
**Reharmonize**. This opens the matching **Input → Reharmonize** tab while retaining
the selection, including when the panel is closed or showing Play. **Generate**
and **Reharmonize** are separate primary tabs; **MIDI** and **Set manually** are
compact additional tools below them. The context menu only opens the controls.

Choose **Find 3 alternatives** to start the search. Each candidate changes at most one chord by default;
**Change up to** also permits two, three, or four. This is a maximum per candidate;
a candidate can change fewer chords. Empty slots and unselected chords stay untouched.
Dragging across empty half-bars is supported: the browser submits and captures
only the written chords. A selection containing no chord symbols remains disabled
and explains that chords must be added or generated first.
Genre is not a search objective, and changing the checkpoint in Reharmonize does
not change the song's genre or playback arrangement.

**Mode → Auto · In context** is the default. It considers familiar substitutions
and their local connections; an explicit parallel mode remains optional and limits
every proposed chord to that scale. Auto does not assign one mode to the whole song.

Four equal cards—**Origin / Alter 1 / Alter 2 / Alter 3**—appear in one row between
the selected passage and the next measure. Select multiple alternatives to preview
their combined changes on the staff, then use the existing Play controls. Clicking
a selected alternative deselects it. If a new choice changes any of the same slots,
it replaces the conflicting alternative as a whole; other selected alternatives
remain. Each preview combines the selected patches over the captured original.
The change limit applies to each alternative; a combination can change more slots.
Combining cards makes no additional Meta call and does not rescore the combination.

**Apply**, directly below **Find 3 alternatives**, keeps the preview and leaves all
cards available. A new combination enables the yellow **Apply** button. After applying,
the button reads **Applied ✓** and the status names the saved combination; returning
to that same combination also shows **Applied ✓**. Choose a different combination
to enable Apply again. Before any alternative is selected, the status explains what
to select. **Origin** previews the exact original symbols and voicings and can
also be applied. The **×** closes the comparison and discards changes made since the
last Apply, preserving later manual edits. A fresh search also discards pending
previews. Autosave retains the last Apply and unrelated edits; reloading clears the
comparison without keeping unconfirmed previews. This is an editor session, not a
saved-project version history.
The controls also show search errors and a **View 3 alternatives on the score**
link, so the comparison remains findable when it is below the visible score rows.

## How candidates are made

1. Muse Spark invokes native `search_substitutions` with a `families` array. The
   first call compares at least two families together: shared tones, parallel-mode
   color, or dominant approaches. This removes an unnecessary network round trip.
2. A bounded deterministic search enumerates sparse patches inside the selection.
   It prunes using shared pitch classes, a symmetric nearest-pitch-class distance
   across neighboring chords, circular bass motion, and parallel scale membership.
   Empty half-bars do not hide the nearest written neighbors within eight measures.
   A small convention prior also favors context-supported borrowed predominants,
   familiar flat-root mixture, and resolving dominant substitutes. Root diversity
   is retained before the per-slot shortlist is trimmed.
   Three- and four-chord searches extend a beam of at most twelve patches with
   two alternatives per selected slot, recomputing the combined context metrics.
   The six-candidate shortlist retains available edit counts so wider changes
   reach the model and Meta instead of being pruned only for changing more chords.
3. The selected Music Transformer scores the shortlists in written order, retaining
   up to eight preceding and eight following measures. Its score includes target
   chords and known later chords. This is causal sequence reranking, not a new
   bidirectional infilling model or explicit modal conditioning. Slash bass is
   evaluated mathematically; the trained tokenizer has no bass tokens.
   Identical token projections are scored once; equal-length sequences run in
   batches of at most three, with every original candidate and exact patch retained.
4. Meta compares returned facts, can explore the remaining family, and calls
   `offer_candidates` with three distinct IDs. It cannot invent an output chord,
   change the score, or call arbitrary functions. The frontend applies the chosen
   sparse patch only after the composer's click.

The convention prior follows examples in Open Music Theory's
[Modal Mixture](https://viva.pressbooks.pub/openmusictheory/chapter/modal-mixture/)
and [Substitutions](https://viva.pressbooks.pub/openmusictheory/chapter/substitutions/):
ii→iiø7, IV→iv, borrowed ♭III/♭VI/♭VII, and resolving dominant/tritone substitutions.
Dorian raised-sixth and locally supported Lydian II colors are also considered;
backdoor dominants receive more support when preceded by iv and resolving to I.
The 0–0.5 weights are hand-authored preferences, not measured usage frequencies.
Only the strongest matching preference per change contributes to the mean bonus;
compatibility with multiple modes does not multiply it. The bonus is already in
`mathScore`. Meta receives `conventionScore` and each change's `conventions` beside
the learned score, and is instructed to balance these when choosing three distinct
options. Candidate cards show the computed convention when one applies.

Pitch-class distance is a heuristic, not measured voice leading or listening
quality. Mode labels describe compatibility with parallel scales of the stated
tonic, not detected modes. The input is chord-symbol context; no melody validation
or audio listening is claimed. Imported augmented sevenths (`Eaug7`, `E+7`, `E7#5`),
suspended sevenths, major extensions, `6/9`, aliases and compound alterations such
as `C7(b9,#11)` retain their exact pitch classes in the mathematical search.
The generated candidate vocabulary remains bounded to the trained/editor qualities.
The music model has only 26 qualities: broader input chords use explicit coarse
encodings (for example `Eaug7` → `E7`) for its score only. `modelApproximations`
discloses these to Meta, the API caller and an expandable note below the candidates.
The original symbols and full tones remain available to Meta and the search; the
projection never edits the score. Unrecognized or ambiguous symbols such as `7alt`
fail before paid calls, naming the measure/slot to correct. Original chord objects
and voicings are retained.

Contextual scoring supports both base checkpoints and genre LoRA models. It calls
the adapted Music Transformer directly, retaining the LoRA and saved embedding/output
modules, instead of passing through PEFT's Hugging Face feature-extraction arguments.
This also fixes Generate failing after composing candidates when a LoRA model must
compare them with already written following chords.

## API and limits

`POST /api/reharmonize` accepts `key`, `timeSignature`, consecutive `context` bars
with two chord slots, `selectedSlots`, `modelKey`, `maxChanges` (1, 2, 3, or 4), and `mode`
(`auto` or one of the seven diatonic modes). A selection may span eight measures
and contain sixteen occupied slots; input context is limited to 256 measures.
API targets must be occupied; the editor filters gaps from a mixed drag selection
before sending the request, without changing the score selection.

The response contains three `candidates` with address/before/after patches and
computed metrics, `modelUsed`, `contextMeasures`, `metaModel`, `requestIds`,
`costUsd`, and `toolCalls`. Scores are ranking signals, not quality probabilities.
Selection and context edits during a request invalidate its result. Later edits
block stale candidate application; Origin may still restore an untouched target
range without removing edits outside it.

Only Meta Standard `muse-spark-1.3` is used. Native calls follow the
[Meta function-calling protocol](https://dev.meta.ai/docs/cookbook/tool-function-calling),
including `tool_choice: auto` and paired assistant/tool messages. Each search is
bounded by four API turns, six function calls, three distinct family searches,
six shortlisted candidates per family, a 30-second per-call timeout, a 100-second
loop deadline, low reasoning effort, 4,096 output tokens per call (including reasoning),
and a $0.15 request reservation cap. Explicit low effort leaves room for the final
candidate IDs; the provider default exhausted the allowance on a four-slot hosted search.
The existing persistent ledger records request IDs, tokens and costs, including
failures; public session and daily limits also apply. Missing models, invalid tool
output, timeout, and budget exhaustion return errors with no success fallback.

## Evidence

The [Korean evaluation synthesis](reharmonization-evaluation.md) brings together
the F4 reference, recommendation-rank and eight-position coverage analysis,
F2/F3 follow-up, model-training distinctions and limitations. Detailed numerical
evidence is under [the selector experiment](../experiments/reharmonization/README.md).
These offline comparisons do not change the three-candidate product controls.

The [synthetic progression record](../experiments/meta/reharmonize_smoke.json)
uses a self-authored three-bar sequence with F4 and actual Meta responses. Three API
requests executed three family searches and a final candidate choice, costing
$0.021142. The alternatives each change one selected slot. This demonstrates the
tool/model integration on one fixture; it is not a listening study.
That paid fixture predates convention scoring. The updated preferences and final
tool payloads are covered with controlled transports, without a new paid Meta run.

Tests cover sparse bounds, both neighboring chords, modes, tensions and slash
basses, validated native calls, spending on failures, combined and overlapping
selections, Apply/cancel/autosave, exact Origin restoration, stale edits, and the
actual staff/comparison markup.
Automated transition tests do not establish audio quality.

The LoRA regression originated in the whole-context scorer added by `1571197`,
before the control-tab split in `c7a042c`: invoking the PEFT wrapper forwarded
Hugging Face arguments that the Music Transformer does not accept. Earlier scorer
tests used stand-in models and missed this integration. The regression test now
uses an actual PEFT-wrapped Music Transformer, checks that the adapter changes the
scores, and verifies that scoring preserves its weights. The `Eaug7` failure was
a separate input-compatibility gap in the substitution search added by `075d12b`.

The [augmented-seventh regression fixture](../experiments/meta/reharmonize_aug7_smoke.json)
uses a self-authored five-bar input with empty bars and `Eaug7`. Actual Classical
LoRA + Meta returned three alternatives with two paid requests ($0.01952950).
An earlier attempt failed when reasoning exhausted the 1,600-token allowance;
its two calls ($0.01513575) remain in the record. The successful allowance is
4,096 tokens; the four-turn, timeout and $0.15 caps remain enforced. All eleven
genre LoRAs plus F2/F3 also completed real local Generate and contextual candidate
scoring. One local generation pass repeated its own short output using the existing
padding behavior; this is functional coverage, not a musical-quality evaluation.

The same fixture also completed through `artist-daw.pearlleestudio.co` with the
Classical LoRA, three candidates and two Meta calls (response cost $0.013937).
Safari Generate returned three Classical LoRA candidates for the previously failing
four-slot selection in an imported score, leaving Original on the staff. In a separate
Chrome verification score on the same deployment, `Eaug7` produced A/B/C, all three
previews updated the staff while retaining the cards, Play reached active audio
playback, and Original restored `Eaug7`. Playback was stopped and loop turned back
off. This confirms the interaction and transport, not listening preference.
