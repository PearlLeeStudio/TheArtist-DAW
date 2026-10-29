# Evaluation plan

What each hackathon addition is measured on, how the "before" and "after" are
defined, and where the numbers live. Every number in this repository follows the
same rules:

- **Same inputs on both sides.** A before/after pair runs the identical fixed
  requests, seeds and limits; only the engine under test changes.
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
| 1 | Note-based harmony (Import, note assistance) | Does the Meta API interpret chords from read notes better than the local analyzer? | `local`: the deterministic analyzer (`score_analysis._inferred_harmony`) | `meta`: Muse Spark over the same notes, 8-bar batches, key given, no printed chords visible · `auto`: local, then Meta only for bars local left unreadable (the product's engine=auto rule) · `openweight`: Muse Spark Open on Baseten, same task | Coverage; root / triad / seventh / bass / exact accuracy on all slots and on covered slots; calibration by reported confidence; latency p50/p95 per call; USD per bar; JSON validity and retry rate (open weight) | Headline set: 8-bar excerpts of the author's private 130-song real-progression test set (Billboard and jazz corpora, not redistributed; aggregates only), realized into notes with the product's own voicing code in six variants (block, rootless, inversion, melody, sparse, waltz). Control set: ~40 synthetic 8-bar scores from the product's own progressions, same variants. Plus one private real score PDF (52 bars, 85 printed symbols, aggregates only) | [experiments/harmony_eval/summary.md](../experiments/harmony_eval/summary.md). Real songs (40 excerpts, 640 slots), exact: local 77.8%, meta 89.5% (+11.7 pp; coverage 100% vs 81.6%; $0.338 for 40 calls, p50 5.1 s), auto 83.9% (+6.1 pp, $0.050 for 6 calls). Local is more precise where it answers (95.4% vs 89.5% on covered slots) and reads no rootless voicing (0% vs 47.3%). Synthetic (42 scores): 77.6 / 79.9 / 78.9%. One real score PDF (37 bars): 18.9 / 29.7 / 21.6%. Open weight (Muse Spark Open on Baseten, effort high): real songs exact 73.8% (coverage 82.5%, 89.4% on covered slots, $0.633 for 40 calls, p50 8.0 s), synthetic 73.1% ($0.670, 44 calls), the real score 0%: each of its 5 calls spent the whole 4096-token output budget on reasoning (`length`), as did 4 of 40 and 4 of 44 calls on the other sets |
| 2 | Complete the form (U1 planner) | Does a Muse Spark plan beat a genre-default form, and does the validate-and-revise loop earn its cost? | `rules` planner: genre-default form, same validator, same generation, no Meta call | `meta` planner: plan → `validate_plan` → ≤2 revisions → section generation → one observe-then-act judgment | First-pass validity; validity after revision and mean revisions; constraint satisfaction on the tight requests; cite correctness (bar and Roman checked by code); judge regenerate rate; p50/p95 latency (plan only, total); USD per run; effort low / medium / high | 20 fixed requests: 10 new songs (5 genres × 2 lengths) and 10 completions of hand-written 8–16-bar sketches, at least 3 with tight constraints | [experiments/agent_eval/summary.md](../experiments/agent_eval/summary.md): Meta at effort medium completed 20/20 runs, first-pass validity 100%, 0 revisions needed, judgment regenerated a section in 45% of runs, $0.0159 and 18.1 s median per run; rules planner 20/20 at $0 |
| 3 | Second-ear review (U2) | Does a model pick among A/B/C better than the R1 order, and are its stated reasons true? | R1 roughness order (the lowest roughness in the review's fact table, and the editor's stored A) | Judge choice with two fact-backed reasons; code checks each `fact` against the analyzer | Agreement with R1 and with stored A; fact-check pass rate; consistency across the three cyclic orders of the candidates; most in-key pick in genres that stay in key; USD per review; latency | The 20 requests of #2, first section each, each in 3 orders (60 reviews per judge) | [experiments/review_eval/summary.md](../experiments/review_eval/summary.md). Muse Spark: reasons confirmed 115/115; lowest-roughness pick 35/60 (58%, random 33%); most in-key pick in diatonic genres 33/36 (92%, R1 pick 67%); same pick in all orders 17/20; $0.0041 and 2.8 s p50 per review. No listening test |
| 4 | Open-weight judge (U6) | Can Muse Spark Open carry the judgment role in the product? | Muse Spark 1.3 (Meta API) | Muse Spark Open (Baseten) in the same role, its own ledger | Same metrics as #1 and #2 judge rows, plus JSON validity / retry rate, request ids from `x-baseten-request-id`, rate-limit headers on 429 | Same data as #1, #2 and #3 | Chord reading ([harmony_eval](../experiments/harmony_eval/summary.md), effort high): real songs exact 73.8%, the real score 0% (every call spent its 4096 output tokens on reasoning). Second ear ([review_eval](../experiments/review_eval/summary.md), effort low): 60/60 with valid JSON and no retry, reasons confirmed 112/112, the same pick as Muse Spark in 52/60, $0.0028 and 2.1 s p50 per review. The planner's judgment was not rerun on open weights |
| 5 | Import reading accuracy (U3b) | How many bars does the local reader get right on real lead sheets? | — (baseline) | — | Bars whose chords match; unresolved bars; seconds per page | Owner-made lead-sheet PDFs with known chords (pending); synthetic PDFs from the test fixture builder as an interim | pending |
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

Structural validity under schema-constrained decoding is easy, so the tight
requests (constraints the genre default cannot satisfy) and the revision loop are
the informative part. `rulesSlots` in each section mark chords rewritten by the
song-form rules; they are excluded from any claim about what the model chose.

## Running

The harness scripts land in this repository together with their first results.

```
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine local       # free
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine meta        # Meta API, ledgered
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine auto
bash scripts/dev.sh py -m scripts.harmony_eval.run --engine openweight  # Baseten, own ledger
bash scripts/dev.sh py -m scripts.harmony_eval.report
bash scripts/dev.sh py agent/plan_and_generate.py --requests experiments/agent_eval/requests --out experiments/agent_eval/results --planner meta
bash scripts/dev.sh py -m scripts.review_eval --judge meta              # Second ear, Meta ledger
bash scripts/dev.sh py -m scripts.review_eval --judge openweight        # Second ear, Baseten, judge ledger
bash scripts/dev.sh py -m scripts.review_eval --report
```

(`scripts/dev.sh` is the author's wrapper; `uv run --directory backend python -m …`
is the equivalent from a checkout.) Each run prints the ledger's `spent_usd`
before and after and stops cleanly at its `--max-usd` limit.
