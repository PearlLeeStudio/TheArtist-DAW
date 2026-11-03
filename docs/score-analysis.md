# Score import, harmony and form

Import prepares source material for the [arrangement workflow](arrangement-workflow.md).
Its output is editable harmony and a form draft, ready for accompaniment and DAW
preparation. Note evidence is used transiently to interpret chords and compare
readings; the editor does not retain extracted notes after that processing or
import them as a melody track.

In **Import Score**, choose the file and optionally check **Use Meta model**, then click
**Analyze and import**. File selection validates size/type and shows the filename;
it does not submit analysis. The checkbox remains selectable while checking a file or
analyzing. Changing it clears the review and aborts an old browser request;
an earlier result cannot populate the new selection. Start the new analysis explicitly.
A provider call already in progress may still finish and incur cost.

The checkbox defaults off (`local`). Checked analysis uses `verified`: one
original-file Meta reading alongside local analysis, followed by comparison or
explicit local recovery if Meta fails. Local processing combines vector-score reading,
deterministic note analysis and, for unresolved passages with readable notes,
bounded F1 harmonization proposals. The checkbox accepts PDF, PNG, JPEG and WebP when
`meta.fullFileScoreImport` is true. File compatibility is checked
when analysis starts, without discarding the selected file.
The REST/MCP request default remains `engine: "local"`; the editor explicitly
sends `mode: "infer_harmony"` and its selected engine.

## Local and Meta comparison

Checked analysis attempts one Meta reading of the original file. It does not
repeat calls until the readers agree or treat a local hypothesis as ground truth.
Deterministic comparison then checks counts, key/meter, chord labels and note
evidence. Aligned printed local symbols and N.C. are preserved. Differences lower
confidence and mark review; agreement never raises confidence or clears a review
flag. Different counts retain the complete local result without aligning bars by
position. If local reading is unsupported, Meta may read the file but the review
reports that local comparison was unavailable. A refused spend admission (session, daily or judge allowance, ledger cap), a disabled
or unconfigured Meta service, or a truncated, timed-out or invalid Meta response
reuses the local reading; the verification note says only that Meta was unavailable
and the reason is logged on the server, so a session allowance below the $1.50
reservation keeps every checked import local. Its result has `local_fallback`
provenance and retains unresolved editable bars; it is never labeled Meta-verified.
If neither reader can provide a review, import reports an error.
An empty Meta chord hypothesis no longer erases an existing local hypothesis;
the local result remains attributed and the disagreement remains visible.
Structured Meta output includes read notes, written notes, bass, meter and N.C.;
these fields are not reconstructed from the chord label.

Meta reading supports at most 128 written bars. A complete locally readable
score can contain up to 512 bars. With **Use Meta model** checked, a local
reading that finishes within two seconds and exceeds 128 bars opens directly with
`local_only` provenance and no Meta call, because Meta's reading could never align
with it; a slower long reading still recovers after Meta's bar-limit failure as
`local_fallback`. Every local bar and its provenance is preserved in both cases.
The unchecked local path makes no Meta call.

In the editor the checked path is two requests. The local reading (`engine:
"local"`) opens the score at once; the same file is then sent as `engine:
"verified"` in the background and its result is applied without replacing
anything visible: disputed bars receive a Review mark carrying the comparison's
reason, bars that are still empty and not N.C. take Meta's one- or two-symbol
proposal with Meta provenance as a single undo step, and `unaligned`,
`local_only` or failed readings only report a summary. The band above the staff
shows the stage, the outcome and the request id; replacing the song discards the
review.

The response's `verification` record reports comparison coverage and zero-based
disputed bars. Reading checks in the existing review show those bars and structural
differences. This adds a way to expose mistakes; no general accuracy improvement
or independent second-model judgment has been established.

The earlier local-first `verified` path read the original one-bar C-major fixture in 17.454
seconds with one Meta call costing $0.007548. It returned one bar, C major, 4/4
and chord C. The comparison flagged that bar because Meta omitted structured note
evidence even though the local reader had pitches; it remained low-confidence and
needed review. Two earlier standalone Meta attempts on this fixture returned 422.
This is a functional example of the combined path and missing-evidence detection,
not a representative accuracy benchmark. The missing structured fields were then
added to the Meta extraction schema. See the [four-condition comparison](score-reader-comparison.md)
for failures, matched inputs and the incremental value of a second review.

## Why a passage can remain unresolved

The deterministic analyzer normally requires three simultaneous structural pitch
classes (with a narrow rootless-shell exception). A melody, dyad or uncertain
duration can therefore remain empty even when adjacent chords suggest a plausible
harmonization. This is distinct from unread notation, an unsupported chord spelling,
or more source changes than the editor's two slots. One source chord already fills
both editor slots; two different chords remain ordered. N.C. is a separate state.

For up to eight empty note-bearing bars in a score of at most 128 bars, local
analysis now calls the served `ft_f1` checkpoint. Three candidate variations use a
fixed sampling seed. Read-note pitch-class overlap ranks them, with the whole-context
model ordering breaking ties. Existing printed/inferred chords and N.C. are retained.
The result says contextual harmonization, keeps low confidence, records `model: ft_f1`,
and uses the read notes only during analysis. Missing weights, unsupported context and bounds are
reported; unread notation never becomes a successful transcription.

The served tokenizer and dataset are causal next-token sequences, without a trained
mask/suffix protocol. Candidate sampling uses preceding chords. When fixed later
chords exist, each completed candidate is scored in written order with all supplied
known bars, including later chords. Target and later-chord mean log likelihood orders
the candidates. This is candidate reranking, not a newly trained bidirectional model.
The model's token window (256 tokens for the served checkpoints) and unsupported chord vocabulary stop that comparison
explicitly; they are never hidden by truncating the suffix. Slash-bass distinctions
remain in the source but are normalized by the trained chord tokenizer.

The same context ranking applies when generating editor variations. It does not
prove a unique original chord or optimal voice leading; it lets fixed later harmony
affect the choice that previously used only preceding bars.

## Bounded API assist

Printed chords and N.C. are preserved. The separate `auto` API mode reviews local inferred harmony
and automatically proposes form in uncovered passages. Valid project metadata
opens the editable score directly after analysis, including unresolved bars;
source details remain available there. Only unusable project fields stop in the
dialog for correction before Import reviewed score.
There is no song-name lookup or stored answer for a particular score.

## Source handling and retention

Use score material you own, that is in the public domain, or that you have
permission to process. The workflow reduces repeated chord entry and preparation
before the DAW; it does not grant arrangement or redistribution rights.

The selected PDF/image is uploaded to the configured TheArtist backend, including
when the reader is called `local`. Here, local means the server's vector-PDF and
harmony analysis without a Meta call; it does not mean browser-only processing.
Checking **Use Meta model** additionally sends the full selected file to Meta.
The separate `auto` API mode sends bounded musical text. Provider handling and
retention remain subject to that provider's terms.

The application's original file and extracted-note data live only for the active
analysis or background comparison. Uploaded files are not written to disk; parsed
scores are not cached between requests. The local reader reparses each upload.
JSON and streaming import responses, including failures, use `Cache-Control:
no-store`. Score-related provider failures retain fixed diagnostics and accounting
metadata rather than provider prose that could repeat the source.

The editor keeps chords, key, meter, section boundaries, playback choices and
minimal reading/review metadata. It removes extracted note arrays and source
evidence from the working Song and saved Projects; existing browser saves are
sanitized while preserving the user's musical work. If the browser refuses the
storage rewrite, the recovered in-memory score remains available and the failed
cleanup is reported; old stored bytes cannot be changed until writes are allowed.
The original PDF/image is
not shown in the editor or saved with the project. Temporary file references are
released after analysis/review, cancellation or close. This is an application
retention policy, not a claim of secure memory erasure or control over a provider's
copy of a request. Model-loading and inference caches are separate and do not
cache uploaded scores.

The earlier decoded-score cache measurements remain in the
[historical performance results](../experiments/speed/runtime-performance.md#import-source);
their cached-reuse speedup is not part of the source-discard workflow.

## Reading notation

`score_pdf.py` reads PDF character transformation matrices and vector lines.
Five-line staff groups establish pitch spacing. Clefs, ledger positions, key
signatures, measure-local accidentals and supported music glyphs establish MIDI
pitch and written spelling. Known legacy notation fonts and recognized SMuFL
codepoints are supported. Staff position is read independently of the instrument;
a lower staff is not assumed to use bass clef.

Barlines group systems and preserve written page order. Printed chord runs are
joined across fonts, including separate accidentals and slash basses. Explicit
N.C. is distinct from an unreadable or unharmonized bar. Repeat-measure signs can
reuse written harmony; D.C./D.S. and ending jumps do not expand the piece.

Stems, beams, flags, dots and rests supply supported durations. Clear ties use
matching staff positions and curve endpoints; a tied accidental can persist
across a barline. A clearly labeled, closed octave bracket can shift sounding
pitches by one or two octaves while retaining `writtenNotes`. Ambiguous slurs,
voice alignment, tuplets and unbounded octave indications
are reported for review. A complete sequence of extracted bars is not a claim
that every pitch, duration or voice has been reconstructed correctly.

## Harmonic interpretation

`harmony_analysis.py` operates on note events, independently of PDF parsing.
It estimates tonal key from weighted pitch durations, with key signature as a
soft preference for a relative major/minor pair. An explicit review key takes
priority. It never treats a key signature alone as proof of major tonality.

Each note start/end creates an analysis slice. Duration, metric position, bass,
voice neighbors and possible passing/neighbor tones contribute to transparent
chord-template scores. At least three sufficiently supported structural pitch
classes must support a complete-chord candidate. Two structural tones a tritone
apart can instead suggest the two possible rootless dominant-seven shells, with
missing root/fifth explicitly recorded and confidence capped at 0.35. The key
orders these alternatives; it does not make either root certain. An ornament
over a dyad cannot manufacture an unrelated confident triad. Missing evidence stays unresolved; alternative chord
interpretations and missing/non-chord tones remain explicit.

Candidates include triads, sevenths and supported extensions, inversions, note
evidence and key-relative Roman numerals. Written roots determine borrowed or
altered scale degrees. Confidence is a heuristic, not a measured accuracy rate.
Unknown rhythm limits confidence instead of being treated as an exact performance.
Roman numerals describe the chord root and quality relative to the selected key
(C, Am, G7 in C major become I, vi, V7). They do not automatically establish
secondary-dominant functions such as V7/vi, tritone-substitution functions or
local modulations; those need a separate analysis of the surrounding progression.

## Meta assist: whole context, bounded review

`engine: "auto", mode: "infer_harmony"` first reads a supported vector PDF.
Each harmony batch receives the complete ordered score synopsis: key and meter,
every bar's printed or inferred chords, confidence, source, N.C. and pitch-class
evidence, plus known section ranges. Detailed notes and neighboring harmony
accompany the target bars. Filenames, lyrics, free-form source annotations and
document images are excluded.

All inferred bars are eligible, including confident local proposals. Printed
chords and N.C. are excluded from replacement. At most two batches of eight bars
are reviewed, with at most 512 notes per batch. The two independent batches run concurrently over the same frozen synopsis,
then form analysis uses their joined results. The remaining bars retain their
local result and are counted as unreviewed. Whole-score context does not mean
every bar was reviewed by Meta. Coverage and nonempty proposals are reported
separately; an empty model proposal does not count as resolved harmony.

The initial complete synopsis must fit 512 bars and 40 KiB; it is rejected before spending
if it cannot fit, rather than truncated. Each serialized harmony/form request is
bounded to 64 KiB, 45 seconds, 4096 completion tokens and $0.10. The combined
assist path permits at most three calls and admits a $0.30 worst case.

After harmony review, one form request uses the complete updated synopsis if any
bar is outside an existing section. Existing ranges, including headings with
`section: null`, are preserved; inferred ranges fill only uncovered passages.
The model may propose up to 32 ranges, each with musical evidence and
`basis: "inferred"`. Plausible boundaries with uncertain function use a neutral
Section label and null type. No defensible structure means an empty proposal
and a visible warning, not invented Intro/Verse labels. The editor presents
automatic results first, with editing and manual additions available.

`formAnalysis: {model, requestId, sectionsProposed}` records this separate form
attempt even when it proposes zero sections. It is null when that step did not
run. Responses distinguish `local`, `meta` and `mixed`; per-bar model/request IDs
keep harmony provenance separate from the form call. Section `basis` becomes
the saved section's origin, so inferred labels remain identifiable.

## Full-file reading and failures

An unsupported local image/PDF never silently switches `auto` to a paid whole-file
request. The checkbox explicitly selects the `verified` full-file path; the
standalone `meta` API mode also remains available. Each sends one
attachment request, bounded to 150 seconds, 32,768 completion tokens, a default
$1.50 reservation cap and 128
result bars. Harmony and form are returned together, without a second form call.
`THEARTIST_PUBLIC_HOST=1` requires `THEARTIST_PUBLIC_META_READER=1` for this path;
without it the route returns 403. The hosted Artist service enables the option.
Local and bounded assist remain available. Session/daily/total spend limits still
apply. Missing or false `meta.fullFileScoreImport` keeps it disabled in the UI.

Direct `meta` and bounded `auto` failures remain errors. The checkbox's `verified`
path can recover a supported local score after Meta fails; it explicitly reports
`local_fallback`, never successful Meta analysis. Disabling Meta leaves local
reading usable; an `auto` request that needs Meta fails with 503.
The ledger records each request ID and usage. Import admission settles only this
request's actual calls, including failures, without counting another caller's
concurrent spending. If settlement cannot be established, the admitted estimate
is retained.

## Review and editor limits

Local input is bounded to an 8 MiB PDF, 50 pages, 512 written measures, limited
page objects/glyphs and 20,000 analyzed note events. Raster scans and unsupported
font encodings need a different reader; they are not presented as locally read.

The analysis can contain more changes than the editor's two equal chord slots.
The score view preserves the source proposals for the selected measure alongside
the editable chord slots and Roman numerals. A bar with more than two source
changes opens with unassigned slots instead of silently dropping changes; all
source symbols remain available for placement. Unsupported symbols leave their
slots unassigned while supported neighboring symbols are retained. These cases
do not block opening the score. Explicit N.C. remains distinct from an unresolved
bar; neither a rest nor a C-major chord is invented for missing evidence.

Source meters remain in the evidence. The current editor uses one global meter;
mixed-meter playback/export is a harmonic sketch and does not reproduce the
source's original timing. Melody notes are analysis evidence, not imported
performance tracks.

Tests cover original geometry and PDF fixtures, translation/scaling, clefs,
accidentals, ties, key changes, transposed harmonies, ornaments, rests, uncertain
timing, source persistence and explicit API boundaries. Passing tests do not
establish universal optical music recognition or guarantee a single correct
harmonization for an ambiguous passage.

The [real import evaluation](../experiments/import_eval/README.md) includes exact
requests, responses and costs for self-authored fixtures. Its 20-bar case retained
four local bars after 16 Meta reviews and inferred three neutral form ranges.
The PNG case read only one of four chords correctly despite high confidence.
Chord reading and uncertain musical form are assessed separately; a completed
API request is not evidence of optical accuracy.
