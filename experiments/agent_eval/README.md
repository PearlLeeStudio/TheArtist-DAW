# experiments/agent_eval — planner evaluation (U3)

The fixed requests, the raw results and the summary of the "Complete the form"
planner evaluation (row 2 of [docs/evaluation.md](../../docs/evaluation.md)).
The runner is [`agent/plan_and_generate.py`](../../agent/plan_and_generate.py).

## requests/ — 20 fixed requests

Each file is one `PlanRequest` body (`backend/app/models/plan.py`), exactly what the
editor sends to `POST /api/plan/song`, without `planner` (the runner sets it). The
file name says what kind of request it is:

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

## results/ — one file per invocation

`rules.json` (the before), `meta-medium.json` (the after, all 20),
`meta-low.json` and `meta-high.json` (the fixed 6-request effort subset). Each
holds the invocation's settings, the clients' provider and model, the ledger totals
before and after, and one record per request with the first-pass validator result,
revisions, final validity, judge decisions and regenerations, latencies, cost,
request ids and the whole trace. No key and no absolute local path is written (the
runner checks the text before writing).

## summary.md

The tables (N, first-pass pass rate, pass rate after revision and mean revisions,
regenerate rate, constraint satisfaction on the tight requests, p50/p95 latency,
cost per run, the effort comparison, the before/after pair) and what they do and do
not show. The tables are the output of `plan_and_generate.py --report`.
