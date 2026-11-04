# Expanded Reharmonize product-agent results

**Scope: existing product tool loop, real F1 weights and actual provider calls. Product code, UX, prompts and runtime configuration were unchanged.**

Frozen schedule: 640 new authored passages × 6 repeats and 40 existing regression passages × 10 repeats, per provider. 8,480 total scheduled executions. Repeats are not new songs. The original 880-run campaign remains separate.

**Partial campaign, deliberately ended after scope review.** After discussion of evaluation scope and submission priorities, the operator ended the remaining Spark 1.3 execution rather than requiring all originally scheduled repetitions. Muse Spark Open had already completed its schedule. Post-hoc: partial results and coverage had already been inspected. This was not a preregistered statistical stopping rule and does not establish a required sample size or prize likelihood.

**2,524 planned executions were not started.** They remain in the original schedule and are not counted as model failures. The unequal full-arm totals below are not a head-to-head success-rate comparison. [Stop decision](stop-decision.json).

| Measurement | Muse Spark Open / Baseten | Muse Spark 1.3 / Meta Standard |
|---|---:|---:|
| Passed / scheduled | 4,186 / 4,240 | 1,673 / 4,240 |
| Started | 4,240 | 1,716 |
| Passed / started | 4,186 / 4,240 | 1,673 / 1,716 |
| Not started | 0 | 2,524 |
| HTTP attempts / extra attempts | 12,504 / 10 | 5,189 / 0 |
| p50 / p95 / p99 seconds | 5.259034 / 8.23852 / 10.591059 | 15.221549 / 24.567953 / 30.557784 |
| Configured-price estimate from returned usage | $28.04348590 | $20.63406350 |
| Unknown-usage reservation | $0.00000000 | $0.09642150 |
| Offers backed by saved tool feedback | 4,186 | 1,673 |
| Offered candidates / finite F1 scores | 12,558 / 12,558 | 5,019 / 5,019 |

## Comparable started rows and input coverage

The following subset retains every outcome for each case/repeat row started by both providers, including failures and operator cancellations. It is selected by execution status, not by success. It remains a partial, non-random prefix of the frozen schedule; it is not evidence of musical superiority.

| Shared case/repeat rows | Open | Spark 1.3 |
|---|---:|---:|
| Started on both providers | 1716 | 1716 |
| Passed | 1680 | 1673 |

| Coverage of authored inputs | Open | Spark 1.3 |
|---|---:|---:|
| Distinct started inputs | 680 | 315 |
| Inputs with at least two started runs | 680 | 281 |
| Observed mode × key mode × complexity × change-limit cells (128 planned) | 128 | 128 |
| Cells with two distinct inputs | 128 | 128 |
| Cells with two distinct inputs each started at least twice | 128 | 105 |

## Cohorts and requested modes

| Cohort / mode | Open passed / scheduled | Spark 1.3 passed / scheduled |
|---|---:|---:|
| regression | 400 / 400 | 0 / 400 |
| auto | 480 / 480 | 239 / 480 |
| ionian | 468 / 480 | 227 / 480 |
| dorian | 480 / 480 | 240 / 480 |
| phrygian | 468 / 480 | 234 / 480 |
| lydian | 474 / 480 | 239 / 480 |
| mixolydian | 480 / 480 | 238 / 480 |
| aeolian | 474 / 480 | 134 / 480 |
| locrian | 462 / 480 | 122 / 480 |

The frozen offline search inspection found fewer than three distinct bounded patches for nine inputs. These cases remain in the full schedule and denominator. Capacity-conditioned counts below describe this limitation; they do not replace the complete-schedule result.

| Search capacity | Open passed / scheduled | Spark 1.3 passed / scheduled |
|---|---:|---:|
| at least three | 4186 / 4186 | 1673 / 4186 |
| fewer than three | 0 / 54 | 0 / 54 |

## Repeated choices and failures

- baseten: 671/680 passages passed all scheduled repeats; 114 returned the same musical offer set on every scheduled repeat. Mean per-passage successful-pair Jaccard overlap: 0.7050240105977811.
- meta: 269/680 passages passed all scheduled repeats; 47 returned the same musical offer set on every scheduled repeat. Mean per-passage successful-pair Jaccard overlap: 0.7226787878787879.

Recorded failed, cancelled, or non-passing started executions: **97**. Unstarted executions: **2524**. All are retained. No failed result was replaced by a paid rerun.

Failure categories, each scheduled row, paired outcomes, request IDs, usage totals and raw-artifact hashes are in [the numeric report](summary.json). Original full requests, provider replies and tool feedback are in the linked compressed JSON trace files. The gzip headers contain no work timestamp.

Combined budget accounting: **$48.77397090**, against the **$120.00** combined cap. Returned token usage is multiplied by the configured rates; unknown usage retains its reservation. These are nominal cost estimates, not confirmed charges, paid invoices or measured credit deductions. Provider credits, sponsorships or discounts are not reconciled here. Meta and Baseten usage is recorded separately.

Hackathon support guidance supplied by the participant places the Baseten key in a separate hackathon workspace with $100 credit expiring November 9 and no provider-side usage or balance view. Personal-dashboard figures therefore do not measure this key. See [credit attribution](README.md#hackathon-credit-attribution); local token accounting does not establish the remaining credit.

## Interpretation and limits

Muse requests searches; the unchanged tools construct candidates and the author's F1 Music Transformer scores their surrounding context. Muse chooses its final three from saved search feedback. The user chooses what to apply in the product. The evaluator stops at the returned offer.

The data are authored engineering fixtures using related templates. The 40 regression passages include a deliberately targeted earlier timeout and are post-hoc evidence. Input-level and repeat-level denominators remain separate. This is not a population estimate over independent songs.

Two evaluation processes per provider, existing adapter differences, local contention and uncontrolled provider caching affect time and cost. These are observed execution measurements, not isolated model speed or musical-quality rankings. Automatic validity, candidate overlap and F1 scores do not establish listening preference. Listening research is planned separately for a paper.

The campaign does not exercise browser interaction, hosted HTTP admission, user application, MIDI export or DAW playback. Full requests reach 512 bars; the existing agent/scorer window remains at most 24 bars. Product code and settings were not changed to improve results.

[Frozen protocol and inputs](README.md) · [Offline verifier](tools/report.py) · [Previous 880-run study](../reharmonize_agent_eval/extended-summary.md)
