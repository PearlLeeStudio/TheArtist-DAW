# Reharmonize product-agent reliability: protocol and evidence

## Product role and measured result

**Meta open weights direct the search. The musician decides what becomes music.**

TheArtist turns a score or chord sketch into harmonic alternatives the musician can audition, apply and carry into a DAW as editable MIDI arrangement parts. The event contribution builds on the author's pre-existing score editor and Music Transformer: it connects score import, contextual harmonic exploration and DAW preparation in one working product.

**The agent contribution is an inspectable musical decision loop.** Muse Spark Open chooses substitution families to investigate, invokes the actual search tools, receives alternatives scored by the author's Music Transformer against the surrounding harmony, and selects three sparse proposals. The tools enforce the selected region and change allowance. The musician chooses and applies a proposal; the resulting harmony feeds editable accompaniment and MIDI export.

**The open-weight contribution is an operational decision-making role.** Muse Spark Open, served by Baseten, directs Reharmonize's tool loop and performs Second ear's candidate review. It is part of the product's inference path. The specialized F1 model supplies contextual scores; Meta controls exploration and the final offer. These responsibilities can be inspected in saved requests, tool feedback, selected candidate bodies and provider usage records.

**Measured reliability: 440/440 Open executions passed every recorded execution and constraint check across 220 authored passages, with two repeats per passage.** The same frozen requests, F1 weights and constraints were also run through Muse Spark 1.3 Standard: 439/440 passed. This is 880 scheduled product-agent executions, including 760 additional runs, with the original Open cohort preserved.

### Evidence a judge can inspect

| Measurement | Muse Spark Open / Baseten | Muse Spark 1.3 / Meta Standard |
|---|---:|---:|
| Passed every recorded check / scheduled | 440 / 440 | 439 / 440 |
| Passages passing both repeats | 220 / 220 | 219 / 220 |
| Runs with search feedback in a model request | 440 | 440 |
| Runs whose entire offer matches saved search feedback | 440 | 439 |
| Offered candidates with finite F1 scores | 1320 / 1320 | 1317 / 1317 |
| HTTP attempts | 1294 | 1319 |
| Extra attempts within tool turns | 0 | 0 |
| p50 / p95 seconds, all started runs | 5.423 / 8.724 | 17.609 / 30.449 |
| Returned-usage cost | USD 3.41593040 | USD 6.70197475 |
| Unknown-usage reservations | USD 0.00000000 | USD 0.03380800 |
| Usage plus unknown-usage reservation accounting | USD 3.41593040 | USD 6.73578275 |

The checks cover model completion, an ending offer, three unique candidate IDs and three distinct applied chord versions, valid addresses, matching original values, preservation outside the selection, change limits, and input immutability. **Runs that did not pass every check: 1.** Every scheduled run remains in the denominator. Full failure details, individual latencies, request IDs, tokens, costs and tool traces are retained in the [paired report](extended-summary.md) and [machine-readable evidence](extended-summary.json). No failed result was replaced by a paid rerun. A failed call without a returned request ID or token usage remains explicitly unknown; a timeout does not count as a completed offer.

The separate Second-ear evaluation completed **60/60 open-weight reviews** over 20 candidate lists in three cyclic orders. **112/112 cited analyzer values** matched computed facts, and **52/60 selections** agreed with Muse Spark 1.3. These measure review execution, factual fidelity and agreement, not listening preference. The earlier hosted Reharmonize evidence is **three repetitions of one Amazing Grace passage**. Neither set is pooled into the 880-run agent rate.

**The product value is continuity from musical intent to editable material.** The sketch supplies context, the agent explores bounded alternatives, the musician makes the harmonic decision, and that decision feeds editable parts for further DAW work. The evaluation measures the harmonic-search stage. Listening evaluation is planned separately for a research paper.

## What was exercised

The evaluator calls the unchanged product entry point, reharmonize_agent.propose(req, client=...), using the normal ContextScorer and real ft_f1 checkpoint. The system prompt, candidate generation, search, scoring, schemas and product settings remain unchanged. A separate evaluation process supplies its own client and cost ledger; the live service's provider configuration is not switched.

This is an in-process product-agent evaluation. Browser interactions, hosted HTTP admission and availability, a user's application of the patch, MIDI export and DAW playback were not exercised. Candidate application is simulated to check that unselected chords survive. It does not establish end-to-end hosted reliability.

The existing compare_reharmonization.py selects from a fixed candidate pool. That is a different experiment and is not used as evidence that this dynamic product tool loop completed.

## Frozen input coverage and grouping

There are **220 distinct authored engineering fixtures**, not 220 sampled songs. Batches A–C contain the original 60 passages. Batches D–K add 160 systematic boundary and notation cases. Each batch contains 20 passages and two full rounds, producing 40 scheduled executions per provider. The paired campaign contains 440 executions per provider, or 880 total.

| Factor | Allocation or coverage |
|---|---|
| Key mode | 110 major, 110 minor |
| Chord complexity | 110 simple, 110 with sevenths, extensions, alterations or slash basses |
| Changed-slot allowance | 55 passages each at limits 1, 2, 3 and 4 |
| Meter | 4/4, 3/4, 6/8, 5/4 and 2/4 |
| Selection | 1–16 slots, contiguous and non-contiguous, within the product's eight-bar span |
| Full request size | 1–512 bars |
| Agent/scorer context | Existing window: selected span plus up to eight bars on each side, at most 24 bars |
| Own model / search mode | ft_f1 / auto throughout |
| Repeats | Two per passage per provider; grouped by passage |

| Batch | Input focus |
|---|---|
| A–C | Original varied frozen passages |
| D | Short 1–3 bar contexts and boundaries |
| E | Empty unselected chord slots |
| F | Maximum 16 selected slots |
| G | Full surrounding context window |
| H | Preservation in 32-, 64-, 128- and 512-bar full requests |
| I | Enharmonic notation, slash bass and extended chords |
| J | Chromatic mixture |
| K | Meter and selections at the ending |

The [original plan](batch-plan.json), [comparison plan](comparison-plan.json) and [expansion plan](expansion-plan.json) retain input hashes and caps. Each cohort's inputs were fixed before that cohort produced model outputs. The expansion uses related harmonic templates; full and effective-window signatures were checked to exclude identical/transposed duplicates. This does not make the fixtures representative or statistically independent. Repeats remain grouped and are never counted as new songs.

The separate [offline input-boundary checks](validation-boundaries.json) rejected 660/660 malformed inputs: 60 source requests with 11 mutations each. They made no model calls and are not included in the 880 paid-agent executions.

## Accounting, limits and comparison

New execution accounting is **USD 9.23217315**, within the **$114 allocation and $120 authorization**. The earlier Open cohort cost USD 0.91954000; combined accounting is USD 10.15171315. Returned-usage cost and unknown-usage reservations are separate in the JSON report. An unknown-usage reservation is a conservative accounting value, not measured provider spend. These totals use configured published rates, not reconciled invoices or an account-balance reading.

Every batch has an independent $6 cap and 40 scheduled rows. A second guard limits each run to $0.15, including retry reservations. Calls are refused before sending when those caps cannot accommodate the reservation. The unchanged product retains four turns, six tool calls, 4,096 completion tokens and its 100-second allowance checked at tool-turn boundaries. The evaluator records observed time overruns rather than promising an exact nested wall-clock cutoff. It adds no retry; HTTP safety ceilings are 12 attempts per Open run and four per Meta run. Unlimited mode is refused.

Both providers use the same requests, own-model weights and constraints. Their existing adapters differ: Baseten uses schema-checked JSON tool turns; Meta Standard uses native function calls. Runs were sequential, cache state and service conditions were not randomized, and the original Open cohort predates its Meta comparison. Time and cost describe those observed product paths, not an isolated model-capability ranking or a guarantee of future service.

All saved response-derived checks were recomputed offline; ledgers, request IDs, tokens, usage costs and frozen hashes were reconciled. The live input-immutability observations remain in the raw records. Existing F1 chord approximations were disclosed in 56 Open runs and 56 Meta runs. Automatic scores and validity checks do not establish musical superiority.

## Reproduction and published files

This directory contains the frozen inputs, all 22 result/ledger pairs, the
original Open-only summary and the combined paired report. The campaign ran once
against the development backend. Copies in the submission package are the same
measured evidence, not additional paid runs. Historical inputs, results and
reported metrics are preserved byte for byte.

- [Frozen evaluator](tools/evaluate_reharmonize_agent.py): offline preflight,
  guarded paid run and offline comparison. Its bytes retain the evaluator hash
  recorded in every result.
- [Offline checks](tools/test_evaluate_reharmonize_agent.py): simulated-provider
  tests and a real-F1 smoke check. Only the checkout-root discovery changed when
  these tools were grouped under experiments for publication.
- [Verify saved results](tools/verify_saved_report.py): recomputes the aggregate,
  response checks, ledger totals, trace observations and costs without a model
  call or overwriting the evidence. It accepts an absolute --backend path.
- [Recorded tools](recorded-tools/): byte-for-byte snapshots of all five scripts
  used to prepare, execute and report the campaign. They retain the original
  workspace paths as provenance; use the entry points above in another checkout.
  The expansion plan's generator hash matches its recorded generator snapshot.
- cases.json and cases-b.json through cases-k.json: the frozen 220 passages.
- open-a through open-k and meta-a through meta-k: the 880 scheduled-run records
  and separate per-attempt ledgers.

Run the offline verifier in the installed development or reconstructed backend
Python environment, with bytecode writes disabled and absolute paths. For example:

    PYTHONDONTWRITEBYTECODE=1 /absolute/backend-python /absolute/checkout/experiments/reharmonize_agent_eval/tools/verify_saved_report.py --backend /absolute/checkout/backend

For the owner's development checkout, invoke that script through the project's
approved dev.sh py wrapper with PYTHONDONTWRITEBYTECODE=1, UV_NO_SYNC=1 and
UV_OFFLINE=1. The submission directory itself is a contribution package: point
--backend at the reconstructed app, with the exact F1 checkpoint available.

The paid evaluator requires a new absolute output directory, provider, approved
cap and the exact input/service/checkpoint hashes printed by preflight. It refuses
existing output directories, unlimited mode and calls beyond the reservation caps.
Credentials come from the process environment only; no dotenv file is loaded or
edited. Atomic writes stay in the output directory; no tmp folder is created.
Reading this evidence or running the offline verifier does not authorize paid
replacement runs. The recorded campaign is complete.

The submission manifest pins the committed development revision and the separate
pre-event core. New evaluation files are inspectable without installation; edits
to existing core files remain in the submission patch. This publication changes
evaluation tools and documentation only. Product code, UX, prompts, scorer,
candidate generation and live model/provider settings are unchanged.

Code remains MIT; the author's weights and training data retain CC BY-NC 4.0.
Automatic measurements do not establish listening preference or musical
superiority, prize likelihood or whether multiple awards can be combined.

## Earlier evidence

- [Hosted Reharmonize traces: one Amazing Grace passage, three repeats](../meta/reharmonize_open_weights_live.json).
- [Second-ear review evaluation: 60 open-weight reviews](../review_eval/summary.md).
- [Existing open-weight roles and evidence](../../docs/open-weights.md).
- [Preserved original 120-run Open-only report](summary.md).
- Provider prices: [Baseten](https://www.baseten.co/pricing/) and [Meta Standard](https://dev.meta.ai/docs/pricing-rate-limits).
