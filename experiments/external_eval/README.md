# External score and harmony evaluation

Real published notation exposes a local-reader limitation: **0/8 editions were supported**.
Three explicit Meta readings returned the right written-bar count, key and meter, but
their harmonic correctness is not established by those structural checks. On the
exploratory Bach note-evidence comparison, only **8/32** proposed pitch-class sets
exactly matched the reference MIDI's note-on pitch classes.

The CPU F1 continuation benchmark also does **not** establish a quality improvement.
Its first candidate agrees less with the selected Mozart reference continuations
than either of the two simple baselines. This task measures reconstruction of one
historical continuation, not whether a different continuation sounds good.

## Published notation

The source manifest contains eight Mutopia editions of seven compositions (two
Greensleeves arrangements), with PDF/MIDI/LilyPond links, hashes, license and maintainer.
The downloaded scores remain outside this repository. No score was added to training,
product retrieval or deployment assets.

| Edition | Local reader | Explicit Meta reader | Written bars / key / meter |
|---|---|---|---|
| Bach BWV 846 Prelude | unsupported; no notes | completed | 35 / C major / 4/4: all agree |
| Bach BWV 847 Prelude | unsupported; no notes | not run | not scored |
| Mozart K.2 Minuet | unsupported; 52 detected regions, no notes | completed | 24 / F major / 3/4: all agree |
| Beethoven Op.2 No.1 Allegro | unsupported; no notes | not run | not scored |
| Schumann Op.68 No.1 | unsupported; no notes | completed | 20 / C major / 4/4: all agree |
| Greensleeves SATB | unsupported; 36 detected regions, no notes | not run | not scored |
| Amazing Grace, bagpipe arrangement | unsupported; no notes | not run | not scored |
| Greensleeves guitar | unsupported; no notes | not run | not scored |

The local failures include missing measure boundaries, clefs and meters. Detected
regions without notes are not successful measures. These findings narrow the
previous self-authored-fixture results; they do not support general LilyPond PDF import.
The default local-plus-Meta mode requires readable local notes and therefore cannot
rescue these files. Explicit whole-file Meta reading is a separate local-only option
and remains disabled on the public host.

The three fixed Meta cases use Standard `muse-spark-1.3`, one request per score,
75-second request timeout, 8,192 output-token ceiling, a $1.35 per-request admission
bound and a $5 persistent batch ledger. Actual total: **3 calls, $0.0761525**, zero
outstanding reservations. Responses, request IDs and token usage are in
[import-results.json](import-results.json). There was no automatic retry or fallback.

Written bars count repeats once, according to the associated LilyPond source.
No expert harmonic labels are available for these particular editions, so the table
does not score inferred chord correctness or confidence calibration.

### Bach note evidence

For BWV 846 bars 1–32, compare the union of each measure's proposed chord pitch classes
with its paired MIDI's note-on pitch classes. The recurring arpeggio layout defines
this subset; the final three bars change texture and are excluded. There is no pickup
or repeat expansion to align. The reference's first two pitch sets are independently
checked against the score: C–E–G and C–D–F–A.

- Exact pitch sets: **8/32 (25%)**.
- Mean pitch precision: **59.69%**; recall: **57.19%**; Jaccard overlap: **48.93%**.
- Every bar, including mismatch and unparseable output, is retained.

This is an exploratory evidence check. Non-chord tones, chord omissions, inferred
extensions and within-measure timing make it different from expert chord accuracy
or note-by-note optical transcription accuracy. Correct bar counts must not be
presented as correct harmony.

## Annotated music continuation

[DCML's Annotated Mozart Sonatas v2.3](https://dcmlab.github.io/mozart_piano_sonatas/)
provides expert harmony annotations. Twelve fixed first movements were selected:
K279, K280, K281, K282, K283, K284, K309, K310, K311, K330, K332 and K545. No selected
movement was excluded by the excerpt checks.

Use the first four written bars as context and predict the next four. Sample each
bar at its start and midpoint. Convert local-key-relative fifths to pitch classes
according to the [ms3 specification](https://ms3.readthedocs.io/en/latest/reference.html).
Context symbols simplify chord type and preserve inversion; reference pitch sets
retain the annotation's chord tones. Changes between the sampled positions, durations,
added tones and voices are not scored.

Actual `ft_f1` on CPU, four threads, OMT ready/Berklee disabled, genre `classical`,
`a_section`, `cadence=none`, seeds 17/18/19: **36 requests, 108 candidates, 864 slots**.
All responses reported `source=ai` and the requested model. This is the product
generation pipeline, including its existing R1 ranking and voice-leading processing.
The first returned candidate A is the primary result, chosen without viewing the
reference; all candidates are also reported, with no best-of-three oracle selection.

| Method | Pitch-set Jaccard | Exact pitch set | Exact root |
|---|---:|---:|---:|
| F1 candidate A, 36 continuations | 36.32% | 13.54% | 22.22% |
| F1 all 108 candidates | 37.84% | 14.70% | 22.57% |
| Repeat final context chord | 43.99% | 27.08% | 37.50% |
| Repeat tonic chord | 56.25% | 46.88% | 42.71% |

All symbols parse after normalizing flat roots/slash bass and `mMaj7`/`maj9` to
music21 notation. An initial metric pass treated some valid notations as invalid;
metrics were recomputed from the **same saved predictions**, without regeneration
or outcome-based selection. The evaluation script includes independent conversion
and chord-spelling anchors. [music-results.json](music-results.json) contains context,
reference sets, predictions, seeds, metrics and source hashes.

The tonic baseline benefits from the tonal opening excerpts. Lower reconstruction
agreement is a limitation for this task, not proof that every generated alternative
is musically bad. One composer, twelve short excerpts, dependent seeds, unknown
training overlap and a jazz/pop-oriented checkpoint limit generalization. This is
not a held-out general music-quality score. Human blind listening and editing-time
measurements remain incomplete.

## Reproduction and attribution

Use the existing backend environment and absolute paths with these runners:

1. `agent/external_eval_sources.py --directory /absolute/eval-data` downloads the fixed sources.
2. `agent/annotated_music_eval.py --backend /absolute/TheArtist-DAW/backend --sources /absolute/eval-data --output /absolute/music-results.json` runs CPU generation.
3. `agent/real_score_eval.py --backend /absolute/TheArtist-DAW/backend --sources /absolute/eval-data --output /absolute/import-results.json` runs local coverage only.
4. Add `--meta-ledger /absolute/private-ledger.json` to step 3 only to authorize the bounded real Meta calls using environment `MODEL_API_KEY`.

Output files must be new; existing evaluations are not overwritten. Both metric
runners accept `--rescore /absolute/saved-results.json` to recompute evidence without
new model calls. Keep raw PDFs/MIDIs/LilyPond, credentials and the timestamped private
cost ledger out of the public repository.

Hentschel, J., Neuwirth, M. & Rohrmeier, M., *The Annotated Mozart Sonatas: Score,
Harmony, and Cadence*, [doi:10.5334/tismir.63](https://doi.org/10.5334/tismir.63).
The annotation-derived reference/prediction evaluation data in `music-results.json`
is distributed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
with the sampling, pitch conversion and metrics described above as modifications.
This noncommercial research artifact is separate from the MIT application code.

Mutopia source attribution and each edition's license are in [sources.json](sources.json).
Bach and Mozart editions used by Meta are public domain; the Schumann edition by
Philippe Hézaine is [CC BY-SA 2.5](https://creativecommons.org/licenses/by-sa/2.5/).
The Schumann-derived reading in `import-results.json` retains that attribution and
license; it is an automated harmony interpretation, not an unchanged score edition.
Other source files were downloaded solely for local support evaluation. No claim
of human listening, general accuracy or musical superiority is made.
