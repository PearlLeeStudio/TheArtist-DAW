# agent/ — planner evaluation

`run_fixed_seed_plans.py` runs controlled rules/Muse Spark pairs on the fixed requests in
[`experiments/agent_eval/requests/`](../experiments/agent_eval/requests/) through
the real service (`app.services.planner.complete_form`, the code behind
`POST /api/plan/song`) in-process, with no server. `report_fixed_seed_plans.py`
validates the saved pairing, generation provenance and costs before pooling the
results. The [controlled comparison](../experiments/agent_eval/fixed-seed/comparison.md)
contains 20 authored fixtures × 3 chord-sampling seeds, or 60 pairs.

`plan_and_generate.py` is the earlier single-arm/effort harness used for
[`experiments/agent_eval/summary.md`](../experiments/agent_eval/summary.md).
Those results did not control chord-sampling seeds and remain separate.

## What one run does

| planner | plan | validate | generate | judge |
|---|---|---|---|---|
| `meta` | Muse Spark (`muse-spark-1.3`, strict JSON) plans the sections after the sketch | code checks the plan; issues go back to the model, at most 2 revisions | the author's chord model writes every planned section in order, with the song-form rules writing each section's first chord and cadence | Muse Spark reads analyzer facts about the model's own chords and may send at most 2 sections back once, at most 2 judgments |
| `rules` | the genre-default form (`planner.RULES_FORMS`) | the same validator | the same generation | none (no LLM call) |

Every Meta call goes through `app.services.llm.LLMClient`: a per-call timeout, a
worst-case reservation per call and per run, the JSON ledger with its cap, request
ids and token usage. The planner's limits (`MAX_META_CALLS` 5, `MAX_RUN_USD` 0.10,
120 s per run) are the product's own. The controlled runner additionally reserves
room for one bounded run before starting it against its dedicated shared ledger.

## Controlled paired runs

`run_fixed_seed_plans.py` forces the same explicit chord checkpoint (`ft_f1`) and
sampling seed within each pair. It records temperatures, RAG and voice-leading
settings; captures every initial/regenerated section's `source` and `modelUsed`;
and stops on a failed run or any service-level rules fallback. Each completed run
is persisted before proceeding. An existing output directory is never overwritten.

The runner uses Standard `muse-spark-1.3` at planning effort `medium` and constructs
its own authorized client from `MODEL_API_KEY`; it does not use the product's
default ledger or its Meta-enabled switch. `--max-usd` must be in `(0, 10]` and
caps the shared evaluation ledger, including previous batches on that ledger.
Run the seeds sequentially so each run's ledger-entry slice stays exclusive.

Replace the absolute example paths with your checkout and workspace paths:

```sh
uv run --directory /path/to/checkout/backend python /path/to/checkout/agent/run_fixed_seed_plans.py \
  --requests /path/to/checkout/experiments/agent_eval/requests \
  --out /path/to/checkout/experiments/agent_eval/fixed-seed/seed-1380 \
  --ledger /path/to/workspace/.tooling/planner-evaluation.json --seed 1380 --model ft_f1 --max-usd 10
```

Repeat with fresh output directories and seeds 1381 and 1382, retaining the same
ledger. The repository's saved directories already exist; use new names for a new
experiment. Generate the report without any API call:

```sh
uv run --directory /path/to/checkout/backend python /path/to/checkout/agent/report_fixed_seed_plans.py \
  --results /path/to/checkout/experiments/agent_eval/fixed-seed/seed-1380 \
  --results /path/to/checkout/experiments/agent_eval/fixed-seed/seed-1381 \
  --results /path/to/checkout/experiments/agent_eval/fixed-seed/seed-1382 \
  --requests /path/to/checkout/experiments/agent_eval/requests
```

The saved main comparison cost $1.020549 for 152 Meta calls. The preserved pilot
cost $0.357468 extra; all four batches reconcile with $1.37801695 and zero
outstanding reservations in the $10 ledger. The pilot is excluded because it
did not retain every generation attempt's source. `fixed-seed/README.md` also
records the seed-1381 shell-wrapper exit error and independent validation of its
complete results.

## Producer and consumer contracts

`POST /api/plan/song` and `/api/plan/song/stream` consume `PlanRequest`, including
optional `seed`: an unsigned 32-bit integer; omitted/null keeps stochastic chord
sampling. It does not seed the Meta planner. A request seed adds `1009 × section
index`, plus `1000003` for regeneration, modulo 2³². The resulting seed is passed
to `SectionGenerateRequest`, also supported by `/api/generate/section` and its
streaming variant. Candidate temperatures 0.7/0.9/1.1 receive offsets 0/1/2 through
request-local random generators. Reproducibility is scoped to the same checkpoint,
runtime, device and sampling parameters.

The paired runner derives the request seed from its base seed plus the first four
SHA-256 bytes of the fixture name. The normalized request bodies must match
exactly except `planner`. Different plans can change section lengths, preceding
context, cadences and therefore neural prompt lengths. This is a comparison of
complete pipelines, including Meta judgments/regeneration, with checkpoint choice
controlled; it does not isolate planning or assess genre-specific LoRA selection.

The reporter consumes `requestBody`, `samplingSeed`, `generationAttempts`,
`apiUsage` and `trace`. It checks all 20 unique fixtures per seed, every generated
section's AI/checkpoint provenance, API-request uniqueness and reconciliation of
run/trace/call/ledger-entry cost. The product `PlanTrace` shape is unchanged.
`status=ok` is execution success, not judge acceptance: 21/60 controlled Meta
runs still ended with a regeneration request. All 60 plans in each arm satisfied
the structural validator; that alone does not establish musical quality.

`export_plan_samples.py --results <seed-directory> --out <fresh-directory>`
consumes three predetermined saved pairs, verifies their request/seed/model/
controls, and renders the saved sketch plus first-ranked final chords. It uses
canonical octave-4 voicing and the product MIDI renderer, never active editor
state. The six [MIDI artifacts](../experiments/agent_eval/fixed-seed/listening/README.md)
have matching paired inputs and verified lengths. No audio listening was
performed. The pitch-collection and repetition diagnostics are proxies; no
musical-superiority or statistical-significance claim is made.

## Earlier single-arm and effort harness

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

## Saved records

The earlier `<out>/<planner>[-<effort>].json` holds the invocation (planner, the three
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

The controlled runner reuses the per-run fields above and adds `requestBody`,
`samplingSeed`, `generationAttempts` and timestamp-free `apiUsage` records.
Its document-level `controls` and `chordModel` are validated across all paired
seeds. It adds no work-date metadata. The strict offline reporter rejects
incomplete or mismatched batches rather than silently pooling a partial result.
