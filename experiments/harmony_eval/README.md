# Harmony evaluation

Does calling the Meta API read chords from notes better than the product's local
analyzer? This folder holds a reproducible comparison on three sets: excerpts of real
songs (private, aggregates only), a public synthetic dataset, and one private real score.
There is one result file per engine and set, and `summary.md` with the tables. The code
is `backend/scripts/harmony_eval/` and its tests `backend/tests/test_harmony_eval.py`.

## Files

| file | what |
|---|---|
| `dataset.jsonl` | 42 synthetic scores (344 bars), written by `scripts.harmony_eval.dataset` with a fixed seed; same seed, same bytes |
| `results-<engine>.json` | one per engine: settings, the dataset's sha256, per-bar outputs for the synthetic scores, aggregate rows for the real score, every call's request id, latency and cost. No keys, no absolute paths |
| `results-real-songs-<engine>.json` | one per engine: aggregates only for the real-song excerpts (overall, per variant, per genre), counts that describe the set, every call's request id, latency and cost. No song, title, id, chord symbol or note |
| `summary.md` | the real-song tables first, then the synthetic results, calibration, per-variant and per-genre breakdowns, the real-score rows, and what the numbers do not show; written by `scripts.harmony_eval.report` |

An engine that could not be built (no API key, Meta switched off) gets a result file
that says so (`not_run`) instead of numbers, and the summary shows that reason.

## Engines

All four get the same note events, the same key, and never a chord symbol.

- **local** — the product's note-based bar analysis, `score_analysis._inferred_harmony`
  (which wraps `harmony_analysis.analyze_harmony` with the product's confidence and
  basis rules). The adapter builds the reader's `ScoreMeasure` / `NoteEvent` objects and
  calls that function; nothing is reimplemented.
- **meta** — `harmony_meta.propose_harmony` through the product's shared client
  (`muse-spark-1.3`, reasoning effort as configured by `LLM_REASONING_EFFORT`, default
  low), over the product's batches: up to 8 consecutive bars and 512 notes per call
  (`score_assistance._next_batch`), notes only, `context=None`. The API never sees the
  truth chords.
- **auto** — the product's `engine=auto` policy, replicated from
  `score_assistance.enrich_local_harmony`: local analysis first; the bars it left without
  chords (and that have notes, at most 512) go to Meta in the same batches, at most
  `MAX_ASSIST_CALLS` (2) calls per score; a Meta proposal keeps its reported confidence
  only when the bar's reading was rhythm-exact and warning-free, else it is `low`. The
  product also sends neighboring *printed* chords as context; here there are none, so the
  context is empty.
- **openweight** — the same notes-only task through an explicitly built client:
  `LLMConfig(provider="baseten", model="meta-models/muse-spark-open-1026",
  reasoning_effort="high")` at Baseten's list price (`llm.BASETEN_PRICES`), key from
  `BASETEN_API_KEY`, its own ledger `backend/.ledger/harmony_eval_baseten.json` capped at
  8 USD, passed through `propose_harmony(client=...)`. The client retries once after a
  reply that is not the requested JSON; the adapter counts attempts, so JSON validity and
  the retry rate are part of the metrics.

Every model call goes through `app.services.llm.LLMClient`, so the ledger records it.
Failures (timeout, HTTP error, invalid JSON after the retry, an unmusical proposal) are
recorded as failures for the batch's bars, never as chords.

## Real songs

The owner's private file of 130 songs held out from training (the paper's evaluation
songs: id, source, genre, title, key such as `Ebmaj` or `Amin`, meter, and per-bar
chord-symbol lists of one to three chords). It never enters this repository, and neither
does anything derived from it except the aggregate result files.

`--songs SONGS.jsonl` (an absolute path outside the repository; there is no default)
loads it with `dataset.load_songs`:

- keeps 4/4 and 3/4 songs and drops the rest (one song, whose meter is unknown);
- writes the key the product's way (`Ebmaj` → `Eb major`, `Amin` → `A minor`);
- writes each chord in the product's spelling (`Ebmaj` → `Eb`, the other qualities as
  the model writes them), and accepts a chord only when the voicing code has a
  chord-tone row for its quality, so no chord is realized as another one;
- keeps a bar with one or two chords (a bar that repeats one chord counts as that chord
  filling the bar) and marks a bar with three or more chords unusable: the editor has two
  slots.

`dataset.build_real_dataset` then cuts each song into one or two eight-bar excerpts
whose every bar is usable (a random run, and a second run that does not overlap it when
the song has one) and picks about 40 excerpts with the seed: every genre present gets an
even share, the remainder going to genres drawn with the seed, and each genre takes one
excerpt per song before any song gives a second. The k-th excerpt of the i-th genre (in
alphabetical order) is realized in variant (i + k) mod 6, with the same six variants and
the same voicing code as the synthetic set, so no genre gets only the easy or only the
hard realizations. A 3/4 song keeps its meter: its two slots are one and a half beats
each.

Keys: the corpus preprocessing writes `Cmaj` for every song whose source has no key
(most of the Chordonomicon-derived genres). Telling the engines "C major" for those would
be false, so for a file key of C major every engine gets the product's own estimate
(`harmony_analysis.estimate_key`) over the excerpt's chords in block voicing instead; the
other excerpts get the song's annotated key. The summary gives both counts.

Where things go:

| what | where |
|---|---|
| the realized dataset (song ids, chords, notes) | `--private-dir`, default `../.tooling/score-inspection/harmony-eval/real-songs-dataset.jsonl` beside the repository |
| per-bar outputs (truth, proposals, evidence) | the same folder, `real-songs-<engine>.jsonl` |
| aggregates, counts, calls | `experiments/harmony_eval/results-real-songs-<engine>.json` |

Guards: `--songs` and `--private-dir` are refused when they resolve inside the
repository (`outside_repo`), and the aggregate file is written only after
`run.assert_aggregate` has checked the whole object: no per-bar field (`chords`,
`truth`, `notes`, `title`, `id`, …), no string that reads as a chord symbol or equals a
song's id, title or any symbol of the set (truth or proposal), and no local path.
`report.py` runs the same check on every real-song file it reads and writes nothing when
one fails.

## Synthetic dataset

`dataset.jsonl`: one JSON record per line with `id, source, progression, genre, key,
timeSignature, variant, bars[{index, chords: [symbol, symbol-or-null], notes[{pitch,
spelling, onset, duration, staff}]}]`. A null second chord means one chord fills the
bar. Onsets and durations are quarter-note beats from the bar start.

Progressions (19): one eight-bar progression per genre from
`chord_generator.generate_suggestions` (seed `20261029 + genre index`, options A/B/C in
turn, keys spread over major and minor, flats and sharps), plus six canonical ones:
ii–V–I in C major, ii–V–i in A minor, I–vi–IV–V in G major, a 12-bar blues in F, a bossa
maj7/m7 loop in D, and a classical period in C major with first-inversion chords.

Realizations (6), using `song_builder._harmony_voicing` / `_bass_pc` and
`voice_leading._CHORD_TONES`: **block** (voicing plus bass root at each of the two slots),
**rootless** (the voicing without its root, no bass), **inversion** (bass on the third or
fifth; the truth symbol carries the slash), **melody** (block plus an eighth-note line of
chord tones with passing and neighbor tones, some non-chord tones on strong beats),
**sparse** (one one-beat chord at the downbeat, then rest; one chord per bar), **waltz**
(3/4: bass on 1, chords on 2 and 3; one chord per bar). Record *n* takes progression
*n mod 19* and variant *n mod 6*, so each variant has 7 records and no progression
repeats a variant.

The voicing table once lacked the quality `m`, so a minor triad written `Am` sounded as
A major; the product fix added it and the dataset was regenerated. A test now checks that
in every block bar each slot strikes the third its truth names (minor for minor and
diminished, major for major and augmented) and not the other one, on the synthetic and
the real-song realizations.

## Metrics

Each symbol is normalized to `(root pitch class, triad maj/min/dim/aug/sus, seventh
family none/maj7/dom7/min7/halfdim7/dim7/sixth, bass pitch class)`
(`chords.normalize`): enharmonics are equal; `m, min, -, dim, °, o, aug, +, sus2/4, 7,
maj7, M7, Δ, Δ9, m7, -7, ø, m7b5, dim7, °7, 6, 6/9, m6` and `9/11/13` (mapped to their
seventh family) are read; `add`, `omit` and alterations are ignored; anything else is
`None` and counts as wrong.

Engine output is aligned to the editor's two slots the way the import fills them
(`chords.align`): one chord fills both slots, two map slot-wise, more than two leaves the
bar unresolved. The truth is aligned the same way.

Per engine, overall and per variant and per genre:

- **coverage** — slots with a proposal.
- **root / triad / seventh / bass / exact** — cumulative: a triad match needs the root, a
  seventh match needs the triad, exact needs root, triad, seventh and bass. Bass is also
  scored on its own, so an inversion heard as the wrong chord over the right bass still
  counts there. Reported on all slots (no proposal = wrong) and on covered slots.
- **unscored truth** — truth slots whose symbol the normalizer cannot read; they are left
  out of every column and counted (`Tally.unscored_truth`) in each engine's status line,
  so they never just shrink the slot count. The synthetic and real-song truths are all
  readable by construction (tested); a printed symbol in the real score may not be.
- **calibration** — root and exact accuracy per reported confidence level
  (`high / medium / low`) on covered slots. Local reports `medium` or `low`; Meta reports
  all three, capped at `low` by the product for bars with fewer than three pitch classes,
  estimated timing or reader warnings.
- **latency** — wall-clock p50/p95 per call: per bar for local, per batch for the model
  engines (auto: its Meta calls only).
- **cost** — the ledger's settled USD per run, and per bar over every dataset bar.
- **JSON validity, retry rate** — replies that parsed as the schema over all attempts, and
  retries per call. The Meta API enforces the schema server-side and the client never
  retries there, so meta's retry rate is 0 by construction.
- **request ids, provider / model** — in the result files (`calls[]`).
- **failed calls** — listed per engine under the results table. A `harmony_validation`
  failure is a schema-valid reply that `harmony_meta` rejected as unmusical (an invalid
  chord symbol, a missing index); its batch's bars count as uncovered, and its cost is
  the ledger's settled amount for that call.

The summary's "Against local" lines give each model engine's difference against local in
percentage points, overall and for its best and worst variant ("no variant scored" when a
run stopped before its first score).

## Real score

`--real SCORE.pdf --private-dir DIR` parses one vector-PDF score with
`score_pdf.parse_vector_score`, keeps the bars that carry both printed chords and read
notes, hides the chords, runs the engine on the notes and scores against the printed
symbols. Bars with more than two printed chords have no two-slot truth and are left out,
as are N.C. bars and bars without notes. The key is the product's own estimate from the
read notes (`harmony_analysis.estimate_key` with the printed key signature), given to
every engine. The per-bar outputs are written only to `DIR` (named after the PDF), which
must be outside the repository; the public file and `summary.md` get aggregate rows
labelled "one private real score, N bars". No PDF and no note data enter the repository.

## Running

From the repository root, with the author's wrapper (from a checkout:
`uv run --directory backend python -m …`):

```
bash scripts/dev.sh py -m scripts.harmony_eval.dataset                     # rewrite dataset.jsonl (same bytes)
bash scripts/dev.sh py -m scripts.harmony_eval.dataset --songs SONGS.jsonl # the real-song dataset, private folder only
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine local          # free; check it looks sane first
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine meta           # Meta API, product ledger
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine auto
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine openweight     # Baseten, own ledger
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine meta --songs SONGS.jsonl
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine meta --real SCORE.pdf --private-dir DIR
bash scripts/dev.sh py -m scripts.harmony_eval.report                      # summary.md
bash scripts/dev.sh backend-test -p 'test_harmony_eval.py'
```

A run prints both ledgers' `spent_usd` (Meta and the open-weight Baseten one) before and
after. `--max-usd` counts the spend already recorded in this folder for the same provider
in the same family of files: the synthetic and real-score files (default 4 for meta and
auto *together*, 8 for openweight), or the real-song files (default 4 for meta and auto
together, 6 for openweight). A run stops cleanly before a call whose worst case
(`harmony_meta.MAX_REQUEST_USD`) could pass it, writes what it has and marks the section
incomplete. The ledger cap (`THEARTIST_META_BUDGET_USD`) still applies underneath. The
synthetic and real-score sections share a results file; each run replaces only its own
section. `THEARTIST_META_ENABLED=0` makes the meta and auto runs report "disabled" and
exit 1. In a sandbox, allow `api.meta.ai` (and `inference.baseten.co` for openweight)
first: a call that cannot reach the host fails as a connection error, and the ledger
settles every such call at its full reservation although nothing was sent.

## What the numbers do and do not show

The real-song excerpts are real progressions held out from training, but their notes are
the product's own voicings of the chord symbols: they test reading real harmony, not a
musician's voicing or a PDF. In the Chordonomicon-derived genres a "bar" is two
consecutive chords as the corpus preprocessing grouped them, not a timed bar. Each genre
holds three or four excerpts in different variants, so compare engines within a row, not
genres with each other. Synthetic realizations of the product's own progressions with
controlled difficulty show *where* an engine fails, not how often a musician's PDF fails.
One real score is evidence, not a benchmark. The key was given; the no-key case is not
measured. Notes only: no printed chords were visible, though the product sends printed
neighbors as context when it has them. A musically defensible alternative (Eb6 for Cm7,
the relative minor for a rootless maj7) counts as wrong against the one truth symbol.
