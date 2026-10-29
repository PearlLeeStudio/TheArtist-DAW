# Evaluation

What each hackathon addition is measured on, how the "before" and "after" are
defined, and where the numbers live. Every number in this repository follows the
same rules:

- **State the controls.** The controlled planner comparison uses identical
  requests, chord-sampling seeds, checkpoint and generation settings in each pair.
  The earlier planner effort study did not control chord-sampling seeds and is
  retained as historical execution evidence, not a paired musical-quality result.
- **Code computes the facts, the model is scored against them.** Chord symbols
  are normalized by code, validator rules are code, analyzer facts are code.
  A model's own claims are never the ground truth.
- **N, cost and limits are always printed next to a number.** Synthetic data is
  labelled synthetic; a private real score contributes aggregate rows only.
- **Failures count.** An unresolved slot, a refused call or an invalid JSON reply
  is a wrong answer in the "all" columns, not a skipped row.
- **The Meta switch.** `THEARTIST_META_ENABLED=0` turns every Meta-backed path
  off at `get_client()`; those paths then report *disabled* (HTTP 503) instead of
  calling the API or pretending to succeed. Evaluation scripts build their own
  clients and still obey the ledger caps.

| # | Addition | Question | Before | After | Metrics | Data (N) | Results |
|---|---|---|---|---|---|---|---|
| 1 | Note-based harmony (Import, note assistance) | Does the Meta API interpret chords from read notes better than the local analyzer? | `local`: the deterministic analyzer (`score_analysis._inferred_harmony`) | `meta`: Muse Spark over the same notes, 8-bar batches, key given, no printed chords visible · `auto`: local, then Meta only for bars local left unreadable (the historical unresolved-only auto rule; current whole-context assist is evaluated separately in row 5) · `openweight`: Muse Spark Open on Baseten, same task | Coverage; root / triad / seventh / bass / exact accuracy on all slots and on covered slots; calibration by reported confidence; latency p50/p95 per call; USD per bar; JSON validity and retry rate (open weight) | Headline set: 8-bar excerpts of the author's private 130-song real-progression test set (Billboard and jazz corpora, not redistributed; aggregates only), realized into notes with the product's own voicing code in six variants (block, rootless, inversion, melody, sparse, waltz). Control set: ~40 synthetic 8-bar scores from the product's own progressions, same variants. Plus one private real score PDF (52 bars, 85 printed symbols, aggregates only) | [experiments/harmony_eval/summary.md](../experiments/harmony_eval/summary.md). Real songs (40 excerpts, 640 slots), exact: local 77.8%, meta 89.5% (+11.7 pp; coverage 100% vs 81.6%; $0.338 for 40 calls, p50 5.1 s), auto 83.9% (+6.1 pp, $0.050 for 6 calls). Local is more precise where it answers (95.4% vs 89.5% on covered slots) and reads no rootless voicing (0% vs 47.3%). Synthetic (42 scores): 77.6 / 79.9 / 78.9%. One real score PDF (37 bars): 18.9 / 29.7 / 21.6%. Open weight (Muse Spark Open on Baseten, effort high): real songs exact 73.8% (coverage 82.5%, 89.4% on covered slots, $0.633 for 40 calls, p50 8.0 s), synthetic 73.1% ($0.670, 44 calls), the real score 0%: each of its 5 calls spent the whole 4096-token output budget on reasoning (`length`), as did 4 of 40 and 4 of 44 calls on the other sets |
| 2 | Complete the form (U1 planner) | What changes when Muse Spark plans and judges the form under controlled chord generation? | `rules`: genre-default form, same validator and `ft_f1` chord checkpoint, no Meta call | `meta`: Muse Spark medium plans → code validates → ≤2 revisions → same chord checkpoint → ≤2 judgments and bounded regeneration | Structural contracts; section-type variety; rule-forced slots; pitch-collection diagnostics; repeated-section symbol agreement; final judge decisions; latency; recorded API cost | 20 public original requests × 3 chord-sampling seeds = 60 pairs; 10 new songs and 10 sketch completions per seed | [Controlled comparison](../experiments/agent_eval/fixed-seed/comparison.md): 60/60 structurally valid in each arm; mean section types 2.75 → 3.48; out-of-key model slots in diatonic genres 19.4% → 14.7% (paired lower/equal/higher 19/4/13); Meta final judge still requested regeneration in 21/60. Main Meta cost $1.020549 for 152 calls, median total latency 17.541 s vs rules 2.040 s. No listening test or musical-superiority claim. [Earlier effort study](../experiments/agent_eval/summary.md) retained separately |
| 3 | Second-ear review (U2) | Does a model pick among A/B/C better than the R1 order, and are its stated reasons true? | R1 roughness order (the lowest roughness in the review's fact table, and the editor's stored A) | Judge choice with two fact-backed reasons; code checks each `fact` against the analyzer | Agreement with R1 and with stored A; fact-check pass rate; consistency across the three cyclic orders of the candidates; most in-key pick in genres that stay in key; USD per review; latency | Twenty candidate lists from the earlier unseeded medium-effort planner run, first section each, in 3 orders (60 reviews per judge); these are not the fixed-seed batches in row 2 | [experiments/review_eval/summary.md](../experiments/review_eval/summary.md). Muse Spark: reasons confirmed 115/115; lowest-roughness pick 35/60 (58%, random 33%); most in-key pick in diatonic genres 33/36 (92%, R1 pick 67%); same pick in all orders 17/20; $0.0041 and 2.8 s p50 per review. No listening test |
| 4 | Open-weight judge (U6) | Can Muse Spark Open carry the judgment role in the product? | Muse Spark 1.3 (Meta API) | Muse Spark Open (Baseten) in the same role, its own ledger | Same harmony and candidate-review metrics as rows 1 and 3, plus JSON validity / retry rate, request ids from `x-baseten-request-id`, rate-limit headers on 429 | Historical harmony fixtures and candidate lists from rows 1 and 3; no fixed-seed planner rerun | Chord reading ([harmony_eval](../experiments/harmony_eval/summary.md), effort high): real songs exact 73.8%, the real score 0% (every call spent its 4096 output tokens on reasoning). Second ear ([review_eval](../experiments/review_eval/summary.md), effort low): 60/60 with valid JSON and no retry, reasons confirmed 112/112, the same pick as Muse Spark in 52/60, $0.0028 and 2.1 s p50 per review. The planner's judgment was not rerun on open weights |
| 5 | Import source flow and failure cases | Do note-based PDF analysis and full-file PNG reading recover the authored chords, and what form suggestions do they produce? | — (four pipeline checks, not a paired benchmark) | Local notes + Meta harmony/form for vector PDFs; Standard Meta full-file reading for PNG | Exact chord comparison; reviewed versus local bars; separate form suggestions; request IDs/tokens/cost | Four self-authored fixtures: C and F single-bar PDFs, a C8→F8→C4 twenty-bar PDF, and a four-bar notes-only PNG | [Import evaluation](../experiments/import_eval/README.md): PDFs 1/1, 1/1 and 20/20 (last four long-PDF bars remained local, not Meta-reviewed); PNG **1/4** despite high confidence. Form ranges are reported separately with no form-accuracy score. 8 calls, $0.04695955. No real-score accuracy claim |
| 6 | Speed gate | Is a 32-bar section generated in ≤ 5 s on the serving host? | before the full-length fix | after | Wall-clock per section, RAG off | `backend/scripts/speed_probe.py` | [experiments/speed](../experiments/speed/) |
| 7 | Whether it works | Do the checks pass and does the manual loop close? | — | — | Backend and frontend test counts, build, lint; the manual checklist | — | [HACKATHON.md](../HACKATHON.md), [docs/manual-checks.md](manual-checks.md) |

## Chord-interpretation metrics (row 1)

A symbol is normalized to `(root pitch class, triad, seventh family, bass pitch
class)`; enharmonics are equal, `add`/alteration text is ignored, an unparseable
symbol is `None`. Engine output is aligned to the editor's two slots per bar the
way the import does: one chord fills both slots, two chords map slot-wise, more
than two leaves the bar unresolved.

- **coverage** — slots with any proposal.
- **root / triad / seventh / bass / exact** — cumulative matches: a triad match
  requires the root, a seventh match requires the triad, exact requires all four.
  Reported *on all slots* (unresolved = wrong) and *on covered slots*.
- **calibration** — accuracy per reported confidence level (`high`, `medium`,
  `low`) where the engine reports one.
- **cost and latency** — from the ledger: settled USD, p50/p95 per call, request
  ids kept with the results.

The synthetic realizations are not real scores: they are the product's own
voicings with controlled difficulty (rootless shells, slash inversions, melody
passing tones, sparse bars, 3/4). They show *where* an engine fails, not how
often a musician's PDF fails. The real-score row is one song; it is evidence, not
a benchmark.

## Planner metrics (row 2)

The genre-default planner satisfies all 20 fixtures, including the four tight
requests. Both arms passed the current validator and requested total length in
all 60 controlled runs. This establishes the structural contract, not an advantage
in musical quality. All initial and regenerated section attempts used `ft_f1`:
282/282 for rules and 331/331 for Meta. Final sections were 282/282 and 274/274 AI
generated; no service-level rules fallback was pooled.

`rulesSlots` marks chords set by deterministic song-form rules. Their shares were
948/4224 (22.4%) and 836/4224 (19.8%); these slots are excluded from the pitch-collection
diagnostic. That diagnostic checks every parsed chord tone, omits slash bass and
allows the union of natural, harmonic and melodic minor in minor keys. It cannot
distinguish an intentional borrowed chord from an unwanted key departure. On the
36 diatonic request-seed pairs, Meta had a lower share in 19, equal in 4 and higher
in 13. Exact repeated-section sequences were 0/132 vs 0/70; symbol agreement was
11.2% vs 12.2%. These measures do not establish thematic consistency or a listening
preference.

The same request body and derived uint32 chord seed are paired, with temperatures
0.7/0.9/1.1, RAG disabled and voice leading enabled. Section length, preceding
context and cadence can change with the plan, so the resulting neural prompts
need not have the same length. Meta planning itself is unseeded. This evaluates
the full planning/judging pipeline with one controlled chord checkpoint, not the
effect of planning alone or genre-specific checkpoint/LoRA selection.

`status=ok` means execution completed. It does not mean that the judge accepted
the result: 32/60 Meta runs regenerated sections, and 21/60 ended with a further
regeneration request after the allowed turns. The judge reads diagnostic reports,
not audio. The three seeds are repeated measurements of 20 authored fixtures;
there is no significance or musical-superiority claim.

The main batches cost $1.020549. The preserved seed-1379 pilot cost an additional
$0.357468 and was excluded because it retained only final section source, not
every generation attempt. Combined ledger spend was $1.37801695 across 203 calls,
within its dedicated $10 cap, with zero outstanding reservations. The existing
[historical comparison](../experiments/agent_eval/comparison.md) uses older saved
runs and has separate historical costs. Offline reporting and the six
[listening MIDI exports](../experiments/agent_eval/fixed-seed/listening/README.md)
made no additional calls. No audio listening was performed.

The producer/consumer contract is documented in [agent/README.md](../agent/README.md):
`PlanRequest.seed` is optional, defaults to stochastic behavior, and seeds only
the local chord generator. The report consumes saved requests, traces, generation
provenance and settled API usage; the MIDI exporter consumes the saved song and
never the active editor state.

## Running

The harness scripts land in this repository together with their first results.

For the controlled planner runs, use `agent/run_fixed_seed_plans.py` with explicit
`--requests`, a fresh `--out`, `--ledger`, `--seed`, `--model ft_f1` and
`--max-usd 10`. Run the seeds sequentially against the same ledger. Then run
`agent/report_fixed_seed_plans.py` with one `--results` per completed seed and the
same `--requests` directory. Full examples and the older effort harness are in
[agent/README.md](../agent/README.md).

```sh
uv run --directory /absolute/path/TheArtist-DAW/backend python -m scripts.harmony_eval.run --engine local
uv run --directory /absolute/path/TheArtist-DAW/backend python -m scripts.harmony_eval.run --engine meta
uv run --directory /absolute/path/TheArtist-DAW/backend python -m scripts.harmony_eval.run --engine auto
uv run --directory /absolute/path/TheArtist-DAW/backend python -m scripts.harmony_eval.run --engine openweight
uv run --directory /absolute/path/TheArtist-DAW/backend python -m scripts.harmony_eval.report
uv run --directory /absolute/path/TheArtist-DAW/backend python /absolute/path/TheArtist-DAW/agent/plan_and_generate.py --requests /absolute/path/TheArtist-DAW/experiments/agent_eval/requests --out /absolute/path/evaluation/planner --planner meta
uv run --directory /absolute/path/TheArtist-DAW/backend python -m scripts.review_eval --judge meta
uv run --directory /absolute/path/TheArtist-DAW/backend python -m scripts.review_eval --judge openweight
uv run --directory /absolute/path/TheArtist-DAW/backend python -m scripts.review_eval --report
```

Use the checkout's backend environment and replace the absolute example paths.
The local harmony run and offline reports make no Meta calls; model-backed
runners need the appropriate provider key and make paid calls. Each runner keeps
its own documented budget controls. Private real-song/score evaluations also need
user-supplied source data; those inputs are not redistributed.
