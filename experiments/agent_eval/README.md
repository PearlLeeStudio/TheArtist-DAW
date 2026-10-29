# experiments/agent_eval — song-form planner evaluation

The fixed requests, raw traces and comparisons for the "Complete the form"
planner (row 2 of [docs/evaluation.md](../../docs/evaluation.md)). The main
[controlled comparison](fixed-seed/comparison.md) uses 20 authored requests ×
3 chord-sampling seeds, with the same `ft_f1` checkpoint in both arms.

| Evidence | Scope | Recorded Meta cost | Interpretation |
|---|---|---:|---|
| [Controlled main batches](fixed-seed/comparison.md) | Seeds 1380/1381/1382, 60 rules/Meta pairs, all initial/regenerated section sources verified | $1.020549, 152 calls | Paired structural and diagnostic comparison of the complete pipelines |
| [Preserved pilot](fixed-seed/README.md) | Seed 1379, 20 pairs, final section sources only | $0.357468, 51 calls | Excluded from the main aggregate because attempt provenance was incomplete |
| [Earlier results](summary.md) and [offline audit](comparison.md) | Earlier unseeded 20-request run and six-request effort subsets | Costs reported in those files | Historical execution/effort evidence; not a controlled musical-quality comparison |

The four live fixed-seed batches used one dedicated $10 ledger: recorded total
$1.37801695 across 203 calls, zero outstanding reservations. Historical runs are
additional, separate costs. Reporting and MIDI export made no further calls.

## requests/ — 20 fixed requests

Each file is one `PlanRequest` body (`backend/app/models/plan.py`), exactly what the
editor sends to `POST /api/plan/song`, without `planner` (the runner sets it). The
controlled runner additionally supplies `modelKey=ft_f1` and an optional uint32
`seed` for the local chord generator. Meta planning is unseeded. The file name
says what kind of request it is:

| prefix | count | what |
|---|---|---|
| `new_<genre>_<bars>` | 10 | a new song: empty sketch, genre defaults for key, tempo and meter; 5 genres (pop, jazz, blues, electronic, gospel) × 2 lengths (32 bars without an outro, 64 with one) |
| `complete_<genre>_<key>_<n>bar_<bars>` | 6 | completion of a hand-written 8- or 16-bar sketch with its locked section(s): pop and rock verses, a jazz A section, a minor-key hip-hop loop, a country verse + chorus, a 16-bar bossa A section |
| `tight_<genre>_<key>_<n>bar_<bars>_<chip>` | 4 | completions whose arithmetic or chips leave the planner little room, so the validator can fail: a 12-bar blues chorus to 48 bars with an outro (36 bars that 12-bar choruses do not divide with an outro last); a 14-bar folk verse + refrain to 16 bars with an outro (the only valid plan is one 2-bar outro); a 10-bar pop verse + turnaround to 32 bars, no outro, contrast high (22 bars); a 12-bar blues chorus to 16 bars, no outro, contrast high (4 bars) |

The sketches are original and simple (I–vi–IV–V pop, ii–V–I jazz, 12-bar blues,
i–VI–VII hip-hop, …). Their Roman numerals are what the editor computes
(`frontend/src/engine/romanNumeral.ts`), checked by
`backend/tests/test_agent_eval_requests.py`, which also validates every file against
the request model and shows that the genre-default (rules) form satisfies each one.

## fixed-seed/ — controlled paired results

Each main seed directory has `rules.json` and `meta-medium.json`, containing the
same 20 normalized requests except for `planner`. Temperatures, checkpoint, RAG
and voice-leading settings are held constant. Section structure, cadence and
preceding context can differ as the effect of the plan, so actual neural prompt
lengths can differ. The shared sampling derivation and API contract are described
in [agent/README.md](../../agent/README.md).

[`run_fixed_seed_plans.py`](../../agent/run_fixed_seed_plans.py) produces the data;
[`report_fixed_seed_plans.py`](../../agent/report_fixed_seed_plans.py) validates
the request pairing, all generation attempts, final section sources and settled
API cost before aggregating it. It rejects incomplete batches. The raw data
includes `requestBody`, `samplingSeed`, `generationAttempts`, `apiUsage`, and the
full `PlanTrace`. Run the live batches sequentially with a shared dedicated ledger
and fresh output directories; product time, turn and per-run cost caps remain in
effect. See [fixed-seed/README.md](fixed-seed/README.md) for the preserved pilot
and seed-1381 wrapper exit error followed by successful independent validation.

Both arms completed and passed structural contracts in 60/60 runs. Every section
attempt used the neural checkpoint: rules 282/282, Meta 331/331. The Meta arm's
mean distinct section types were 3.48 versus 2.75; out-of-key model slots in the
diatonic subset were 14.7% versus 19.4%, with paired lower/equal/higher counts
19/4/13 over 36 request-seed pairs. However, 21/60 final Meta judge decisions still
requested regeneration. The judge reads diagnostic reports, not music.

These are repeated measurements of 20 fixtures, not 60 independent musical tasks.
The pitch-collection diagnostic can penalize valid borrowed harmony, repeated
symbol agreement is not a thematic-coherence score, and fixed `ft_f1` does not
evaluate genre-specific model/LoRA selection. [Six listening MIDI files](fixed-seed/listening/README.md)
preserve three predetermined paired examples with identical playback settings.
No audio listening or preference measurement was performed, and no musical
superiority or significance is claimed.

## results/ — earlier single-arm and effort runs

`rules.json` (the before), `meta-medium.json` (the after, all 20),
`meta-low.json` and `meta-high.json` (the fixed 6-request effort subset). Each
holds the invocation's settings, the clients' provider and model, the ledger totals
before and after, and one record per request with the first-pass validator result,
revisions, final validity, judge decisions and regenerations, latencies, cost,
request ids and the whole trace. No key and no absolute local path is written (the
runner checks the text before writing).

## summary.md — earlier effort-study summary

The tables (N, first-pass pass rate, pass rate after revision and mean revisions,
regenerate rate, constraint satisfaction on the tight requests, p50/p95 latency,
cost per run, the effort comparison, the before/after pair) and what they do and do
not show. The tables are the output of `plan_and_generate.py --report`. The
controlled 60-pair results are in [fixed-seed/comparison.md](fixed-seed/comparison.md)
and do not replace or alter these earlier raw files.
