# Local score analysis

Selecting a file in Import Score automatically starts local code analysis, with
an indeterminate progress indicator until the response arrives. Printed chord
symbols take priority; note-based harmony is proposed only where symbols are
absent. Valid project metadata enables Import reviewed score without a separate
checkbox; clicking it opens the editable score, including unresolved chord bars.
The dialog contains no chord-analysis list. Reading a supported vector PDF and analyzing
its notes requires no model key, API call, file upload or network connection.
There is no song-name lookup or stored answer for a particular score.

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

## Optional Meta assistance

The import screen always sends `engine: "local"`; it has no Meta option and never
automatically calls an external model. The API retains the bounded Meta capability
for future work. For API callers, `engine: "local"` is the default. Selecting `auto` explicitly permits Meta when
the format is unsupported or local harmony is unresolved. Locally read note
events can be sent as musical text for interpretation; filenames, lyrics and
document images are excluded from that assistance path. It uses at most two
calls per import, eight measures and 512 notes per call, 64 KiB of serialized
musical context, 45 seconds, 4096 completion tokens and a $0.10 reservation cap
per call. The shared spend ledger records actual request IDs and usage.

An unsupported local image/PDF can instead use the existing bounded Meta document
reader after explicit selection. That path sends the chosen attachment, has a
75-second timeout, a $1.35 reservation cap and a 128-bar result limit. A provider,
configuration or budget failure stays an error. There is no successful-looking
random fallback. All Meta harmonic interpretations require review.

Responses distinguish `local`, `meta` and `mixed`. Per-bar source, note/bass
evidence and request identifiers preserve the boundary between local reading
and model interpretation.

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
