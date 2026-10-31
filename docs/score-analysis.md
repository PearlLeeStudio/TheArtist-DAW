# Score import, harmony and form

In **Import Score**, choose the file and Reader in either order, then click
**Analyze score**. File selection validates size/type and prepares a local preview;
it does not submit analysis. Reader remains selectable while checking a file or
analyzing. Changing Reader clears the review and aborts an old browser request;
an earlier result cannot populate the new selection. Start the new analysis explicitly.
A provider call already in progress may still finish and incur cost.

The editor defaults to **TheArtist + Meta** (`auto`) when discovery reports Meta
enabled and configured; otherwise it uses **TheArtist only** (`local`). TheArtist
here means the local score reader, not the composition Transformer. **Meta only**
(`meta`) accepts PDF, PNG, JPEG and WebP when `meta.fullFileScoreImport` is true.
Files can be selected before their compatible Reader; compatibility is checked
when analysis starts, without discarding the selected file.
The REST/MCP request default remains `engine: "local"`; the editor explicitly
sends `mode: "infer_harmony"` and its selected engine.

Printed chords and N.C. are preserved. Meta assist reviews local inferred harmony
and automatically proposes form in uncovered passages. Valid project metadata
enables Import reviewed score without a separate checkbox. The button opens an
editable score, including unresolved bars; source details remain available there.
There is no song-name lookup or stored answer for a particular score.

The file is sent to the configured TheArtist backend. Local vector-PDF analysis
needs no model key or external provider call. Meta assist sends bounded musical
text to Meta; Full file sends the chosen attachment. Uploaded file bytes are not
stored in the project. Parsed local results have a bounded in-memory cache
(four entries, 8 MiB total, five-minute TTL), keyed by PDF digest and parsing
limits; each caller gets an independent result. Raw bytes are not retained by
that cache. See [performance measurements](../experiments/speed/runtime-performance.md).

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
request. Choose **Meta only** explicitly to use that reader. It sends one
attachment request, bounded to 75 seconds, 8192 completion tokens, $1.35 and 128
result bars. Harmony and form are returned together, without a second form call.
`THEARTIST_PUBLIC_HOST=1` requires `THEARTIST_PUBLIC_META_READER=1` for this path;
without it the route returns 403. The hosted Artist service enables the option.
Local and bounded assist remain available. Session/daily/total spend limits still
apply. Missing or false `meta.fullFileScoreImport` keeps it disabled in the UI.

Configuration, budget, provider and validation failures stay errors. There is no
successful-looking local fallback after an attempted Meta analysis. Disabling
Meta leaves TheArtist only usable; an `auto` request that needs Meta fails with 503.
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
