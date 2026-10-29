# agent/ — planner evaluation runner

`plan_and_generate.py` runs the fixed planner requests in
[`experiments/agent_eval/requests/`](../experiments/agent_eval/requests/) through
the real service (`app.services.planner.complete_form`, the code behind
`POST /api/plan/song`) in-process, with no server, and writes one results file per
invocation. The numbers in
[`experiments/agent_eval/summary.md`](../experiments/agent_eval/summary.md) come
from these files.

## What one run does

| planner | plan | validate | generate | judge |
|---|---|---|---|---|
| `meta` | Muse Spark (`muse-spark-1.3`, strict JSON) plans the sections after the sketch | code checks the plan; issues go back to the model, at most 2 revisions | the author's chord model writes every planned section in order, with the song-form rules writing each section's first chord and cadence | Muse Spark reads analyzer facts about the model's own chords and may send at most 2 sections back once, at most 2 judgments |
| `rules` | the genre-default form (`planner.RULES_FORMS`) | the same validator | the same generation | none (no LLM call) |

Every Meta call goes through `app.services.llm.LLMClient`: a per-call timeout, a
worst-case reservation per call and per run, the JSON ledger with its cap, request
ids and token usage. The planner's limits (`MAX_META_CALLS` 5, `MAX_RUN_USD` 0.10,
120 s per run) are the product's own and are recorded in each results file.

## Running

From the repository root, with the backend set up (`uv sync` in `backend/`) and
`MODEL_API_KEY` in the environment for the meta planner:

```
# the "after": Muse Spark plans at the planner's own effort (medium), all 20 requests
uv run --directory backend python ../agent/plan_and_generate.py \
    --requests ../experiments/agent_eval/requests --out ../experiments/agent_eval/results --planner meta

# the "before": genre-default forms through the same validator and generation, no Meta call
uv run --directory backend python ../agent/plan_and_generate.py \
    --requests ../experiments/agent_eval/requests --out ../experiments/agent_eval/results --planner rules

# the plan-effort comparison on the fixed 6-request subset (EFFORT_SUBSET in the script)
uv run --directory backend python ../agent/plan_and_generate.py ... --planner meta --effort low --subset
uv run --directory backend python ../agent/plan_and_generate.py ... --planner meta --effort high --subset

# the summary tables (markdown) from every results file in --out
uv run --directory backend python ../agent/plan_and_generate.py --report --out ../experiments/agent_eval/results
```

(The author's wrapper is `bash scripts/dev.sh py <absolute path to the script> …`,
which runs the same `uv run --directory backend python`.)

Options:

- `--effort low|medium|high` sets the *planning* effort only; revisions and the
  judge keep the planner's own efforts (low), so the comparison changes one thing.
- `--max-usd N` (default 6): the invocation stops before a run that could pass this
  spend, counting a run at its worst-case cap (`planner.MAX_RUN_USD`). The product
  ledger's cap (`THEARTIST_META_BUDGET_USD`) applies underneath. The ledger's
  `spent_usd` is printed before and after.
- `--subset`: only the fixed effort-comparison subset.
- `THEARTIST_META_ENABLED=0` makes every meta run fail as *disabled* after the
  first; the failure is recorded and the invocation stops.

Exit status is 0 when every requested run completed, 1 when the invocation stopped
early or any run failed. The results file is rewritten after every run, so an
interrupted invocation keeps what it finished.

## What is recorded

`<out>/<planner>[-<effort>].json` holds the invocation (timestamp, planner, the three
efforts, the planner limits, the clients' provider and model with no key, the
ledger totals before and after, the spend of this invocation, why it stopped if it
did) and one record per request:

| field | meaning |
|---|---|
| `firstPass` | the validator's verdict on the first plan: `ok` and the issue codes |
| `revisions` | validation attempts after the first (0–2) |
| `planValid` | whether the last validated plan passed |
| `plan`, `cites`, `citeErrorsFirstPass` | the final plan's sections, how many sketch bars it cites, cite issues on the first pass |
| `judge`, `regenerated` | each judgment's decision; sections regenerated |
| `planMs`, `totalMs`, `metaMs`, `generationMs` | plan phase (to its last validation), whole run, wall clock inside LLM calls, inside the chord model |
| `costUsd`, `planCostUsd`, `reservedUsd`, `requestIds` | settled cost (failed calls included), the plan calls' share, worst-case reservations, every request id |
| `events` | the run's step timeline, `[event, ms]` |
| `trace` | the whole `PlanTrace` as the API returns it |

The file is checked before it is written: a value of any key variable in it aborts
the write, and the repository path is replaced by `<repo>`.
