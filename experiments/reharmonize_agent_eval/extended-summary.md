# Expanded product-agent reliability: paired Meta paths

The unchanged Reharmonize agent was exercised on **220 authored passages, twice per provider: 880 scheduled executions**. This combines the preserved first 120 Muse Spark Open runs with 760 newly approved executions. Results below describe execution and constraints, not musical preference.

| Measurement | Muse Spark Open / Baseten | Muse Spark 1.3 / Meta Standard |
|---|---:|---:|
| Started / scheduled | 440 / 440 | 440 / 440 |
| All execution and constraint checks passed | 440 / 440 | 439 / 440 |
| Passages passing both repeats | 220 / 220 | 219 / 220 |
| HTTP attempts | 1294 | 1319 |
| Extra attempts within tool turns | 0 | 0 |
| p50 / p95 latency, all started runs | 5.423 / 8.724 s | 17.609 / 30.449 s |
| Returned-usage cost | $ 3.41593040 | $ 6.70197475 |
| Unknown-usage reservations | $ 0.00000000 | $ 0.03380800 |
| Accounted usage and unknown-usage reservations | $ 3.41593040 | $ 6.73578275 |

New execution accounting: **$9.23217315**, within the $114 allocation and $120 authorization. The previous Open run cost was $0.91954000. Unknown-usage reservations are recorded separately in the machine-readable report; they are not measured provider spend.

## Per-batch results

Each row contains 20 passages and 40 scheduled runs per provider. Batches A–C are the original 60 fixtures; D–K are the later systematic expansion, fixed before those batches produced model outputs.

| Batch / input focus | Open passed / 40 | Meta passed / 40 | Both paths passed / 40 |
|---|---:|---:|---:|
| A / original frozen inputs | 40 | 40 | 40 |
| B / original frozen inputs | 40 | 40 | 40 |
| C / original frozen inputs | 40 | 40 | 40 |
| D / short-boundaries | 40 | 40 | 40 |
| E / empty-unselected-slots | 40 | 40 | 40 |
| F / sixteen-selected-slots | 40 | 40 | 40 |
| G / full-surrounding-window | 40 | 39 | 39 |
| H / long-score-preservation | 40 | 40 | 40 |
| I / notation-and-slash-bass | 40 | 40 | 40 |
| J / chromatic-mixture | 40 | 40 | 40 |
| K / meter-and-ending-selection | 40 | 40 | 40 |

## Model role visible in the saved traces

These descriptive counts were derived offline from the existing records. They are not additional pass criteria and do not require new model calls. Tool messages are deduplicated within each run before checking whether full offered candidate bodies appeared in the search feedback.

| Trace observation | Open | Meta Standard |
|---|---:|---:|
| Runs with search feedback in a model request | 440 | 440 |
| Runs whose whole offer matches saved search feedback | 440 | 439 |
| Offered candidates | 1320 | 1317 |
| Offered candidates with a finite F1 model score | 1320 | 1317 |

The machine-readable report also lists the model's requested search-family combinations and tool names. This makes the division of work inspectable: Meta requests searches and selects the offer, the unchanged search tools produce bounded candidates, and the author's F1 model supplies contextual scores. These observations establish recorded execution, not that a chosen candidate sounds better.

## Failures and scope

**Runs that did not pass every check: 1.** Every one remains in the denominator and in [the failure list](extended-summary.json); no replacement run was used to improve the reported result.

| Provider | Passage / repeat | Recorded error or failed checks | Run seconds | Unknown-usage reservation |
|---|---|---|---:|---:|
| meta | g-minor-03 / 1 | LLMTimeout | 37.143 | $ 0.03380800 |

A request timeout leaves completion unproven and counts as a failed run. When a failed HTTP attempt returns no usage or request ID, those values remain unknown; its conservative reservation is reported separately from returned-usage cost. HTTP error types, attempt positions and durations remain in the JSON failure list and raw traces.

- Muse Spark Open: no recorded errors. Existing F1 chord-scoring approximations were disclosed in 56 returned runs.
- Muse Spark 1.3 Standard: LLMTimeout: 1. Existing F1 chord-scoring approximations were disclosed in 56 returned runs.

- Authored engineering fixtures with related harmonic templates; not representative corpus samples or independent songs.
- Two repeated runs per passage and provider remain grouped; automatic measurements do not establish listening preference or musical superiority.
- In-process unchanged product paths. Browser UX, user application, hosted admission/availability, MIDI export and DAW playback were not exercised.
- Existing Baseten JSON-tool and Meta native-tool adapters differ. Timing and cost are observations of those paths, not an isolated capability comparison.
- Sequential, non-concurrent runs; original Open observations precede the comparison. Cache state and provider conditions were not randomized or equalized.
- Up to 512 bars in the full request; the unchanged product exposes at most the selected eight bars plus eight surrounding bars per side to its agent/scorer.
- Usage-based costs use configured published rates and are not reconciled invoices or account-balance measurements.

The separate offline boundary checks rejected **660/660 malformed inputs** without a model call. These are not included in the 880 paid-agent executions. Listening evaluation is planned separately for a research paper.

## Evidence

- [Full combined summary, paired outcomes, strata, failures and artifact hashes](extended-summary.json).
- [Original Open-only report](summary.md), preserved as its own completed cohort.
- [Comparison plan](comparison-plan.json), [expansion plan](expansion-plan.json), and [offline validation checks](validation-boundaries.json).
- Every full request, tool turn, response and per-attempt ledger remains in the corresponding `open-a` through `open-k` and `meta-a` through `meta-k` result folders.
- Prices: [Baseten](https://www.baseten.co/pricing/) and [Meta Standard](https://dev.meta.ai/docs/pricing-rate-limits).

Input hashes, product code, evaluator and F1 checkpoint matched the frozen plans. Saved response-derived constraints were recomputed offline; per-attempt records were reconciled with each ledger and usage costs recalculated. The live input-immutability observations remain in the raw records. No API call was needed for reporting.

The earlier three Amazing Grace hosted Reharmonize runs and the separate 60 Second-ear reviews remain separate evidence. They are not pooled into this paired execution rate.
