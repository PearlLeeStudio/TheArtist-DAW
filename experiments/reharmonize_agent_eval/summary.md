# Muse Spark Open: product-agent execution reliability

**120/120 agent executions passed all recorded execution and constraint checks
across 60 frozen authored harmonic passages, each run twice.** All 60 passages
passed on both repeats. Muse Spark Open directed the unchanged product agent's
tool loop, using the real `ft_f1` Music Transformer scorer. This measures
execution reliability on these inputs; it does not establish listening
preference, musical superiority or award eligibility.

The model was `meta-models/muse-spark-open-1026` on Baseten, with the existing
`low` reasoning setting. Product code, prompts, search, scoring, candidate
generation, UX and deployed provider settings were unchanged. This was an
independent in-process evaluation, not a change to the hosted service.

| Measurement | Observed result |
|---|---:|
| Scheduled / started / passed executions | 120 / 120 / 120 |
| Distinct authored passages / both repeats passed | 60 / 60 |
| Three candidates with unique IDs and different applied chord versions | 120/120 runs |
| Selected-region preservation and change-limit compliance | 120/120 runs |
| Valid addresses, matching original chords and unchanged request | 120/120 runs |
| Model completion ending in `offer_candidates` | 120/120 runs |
| Failed / unstarted / local-selection runs | 0 / 0 / 0 |
| HTTP attempts / distinct recorded request IDs | 352 / 352 |
| Extra attempts within tool turns | 0 |
| Latency p50 / p95, all 120 started runs | 5.430 s / 9.323 s |
| Observed runs within 100 seconds | 120/120 |
| Cost calculated from returned token usage | $0.91954000 |
| Unknown-usage reservations / outstanding reservations | $0 / $0 |
| Approved campaign ceiling | $18, three independent $6 batches |

Candidate diversity is checked within each run by the resulting chord roots,
pitch classes and basses; differently named IDs alone do not count as different
versions. Latency includes local scoring and any provider attempts. The combined
percentiles use all individual observations, not averages of batch percentiles.

| Frozen batch | Passages | Passed / scheduled | HTTP attempts | Usage cost | p50 / p95 |
|---|---:|---:|---:|---:|---:|
| A | 20 | 40/40 | 116 | $0.29033515 | 5.293 / 8.305 s |
| B | 20 | 40/40 | 118 | $0.30808435 | 5.357 / 8.765 s |
| C | 20 | 40/40 | 118 | $0.32112050 | 6.003 / 9.562 s |

The inputs cover 30 major and 30 minor passages, 30 simple and 30 complex
progressions, and 15 passages at each change limit from one to four slots.
Contexts contain four to eight bars, with five meters and varied selections.
Inputs were fixed before observing these model outputs. They are authored
engineering fixtures, not a sample of 60 independent songs. Two repeats share
each passage and must not be counted as 120 independent songs. No failed or
unfavorable result was replaced by an extra paid rerun.

The product reported existing F1 scoring approximations in 36 runs over 18
passages, such as scoring a richer extension as a supported simpler chord.
Those disclosures remain in every full response. Constraint compliance does
not imply that F1 represents every extension exactly.

There were 861,717 prompt tokens, including 560,640 cached prompt tokens, and
108,023 completion tokens. The 94,155 reported reasoning tokens are a subset
of completion usage and are not charged a second time in this calculation.
The configured rates match the [Baseten price table](https://www.baseten.co/pricing/):
$1.25 per million uncached input tokens, $0.15 per million cached input tokens
and $4.25 per million output tokens. The cost is usage-based accounting, not a
reconciled provider invoice or an account-balance measurement.

## Inspectable evidence

- [Frozen campaign plan](batch-plan.json) and inputs
  [A](cases.json), [B](cases-b.json), [C](cases-c.json).
- Full requests, provider replies, tool turns, candidates, errors, audits and
  request IDs: [A](open-a/results.json), [B](open-b/results.json),
  [C](open-c/results.json).
- Per-attempt reservation and settlement ledgers: [A](open-a/ledger.json),
  [B](open-b/ledger.json), [C](open-c/ledger.json).
- [Machine-readable combined summary](summary.json), including strata,
  input/result/ledger hashes, cost totals and verification outcomes.
- [Evaluation protocol and README wording draft](README.draft.md).

The completed reports match the frozen inputs, evaluator, product-service code
and F1 checkpoint hashes. Every saved response-derived constraint was recomputed
offline. All per-run ledger entries match the batch ledgers; all 352 request IDs
are present and distinct. Token costs were recalculated independently, and
exported records were checked for the executing credentials. No additional
model call was made for these checks.

This evaluation excludes browser interaction, user application of a proposal,
HTTP admission, deployment availability, MIDI export and DAW playback. The
Muse Spark 1.3 comparison arm has not been executed. Listening evaluation is
planned separately for a research paper.

The earlier three hosted Reharmonize runs remain three repetitions of one
Amazing Grace passage. The separate Second-ear evidence remains 60 reviews
over 20 candidate lists in three cyclic orders. These records are separate
tasks and are not combined into one cross-task success rate.
