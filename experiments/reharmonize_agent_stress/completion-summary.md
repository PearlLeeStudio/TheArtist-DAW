# Expanded Reharmonize product-agent results

The participant explicitly requested finishing the original Spark 1.3 schedule after the operator stop. Only originally unstarted rows were scheduled; the earlier failure and cancellation records are unchanged. The [partial report](summary.md), [earlier stop decision](stop-decision.json) and [continuation plan and row mapping](continuation/README.md) remain available. The temporal break and smaller accounting batches limit comparisons of timing and caching.

**Scope: existing product tool loop, real F1 weights and actual provider calls. Product code, UX, prompts and runtime configuration were unchanged.**

Frozen schedule: 640 new authored passages × 6 repeats and 40 existing regression passages × 10 repeats, per provider. 8,480 total scheduled executions. Repeats are not new songs. The original 880-run campaign remains separate.

| Measurement | Muse Spark Open / Baseten | Muse Spark 1.3 / Meta Standard |
|---|---:|---:|
| Passed / scheduled | 4,186 / 4,240 | 4,144 / 4,240 |
| Started | 4,240 | 4,240 |
| Passed / started | 4,186 / 4,240 | 4,144 / 4,240 |
| Not started | 0 | 0 |
| HTTP attempts / extra attempts | 12,504 / 10 | 12,779 / 0 |
| p50 / p95 / p99 seconds | 5.259034 / 8.23852 / 10.591059 | 15.553459 / 26.903452 / 35.385782 |
| Configured-price estimate from returned usage | $28.04348590 | $52.30077735 |
| Unknown-usage reservation | $0.00000000 | $0.91077275 |
| Offers backed by saved tool feedback | 4,186 | 4,144 |
| Offered candidates / finite F1 scores | 12,558 / 12,558 | 12,432 / 12,432 |

## Comparable started rows and input coverage

Every original case/repeat row has now been started by both providers. The comparison retains all failures and the original operator cancellation. These authored, repeated fixtures are not a random sample of music, and the results do not establish musical superiority.

| Shared case/repeat rows | Open | Spark 1.3 |
|---|---:|---:|
| Started on both providers | 4240 | 4240 |
| Passed | 4186 | 4144 |

| Coverage of authored inputs | Open | Spark 1.3 |
|---|---:|---:|
| Distinct started inputs | 680 | 680 |
| Inputs with at least two started runs | 680 | 680 |
| Observed mode × key mode × complexity × change-limit cells (128 planned) | 128 | 128 |
| Cells with two distinct inputs | 128 | 128 |
| Cells with two distinct inputs each started at least twice | 128 | 128 |

## Cohorts and requested modes

| Cohort / mode | Open passed / scheduled | Spark 1.3 passed / scheduled |
|---|---:|---:|
| regression | 400 / 400 | 383 / 400 |
| auto | 480 / 480 | 478 / 480 |
| ionian | 468 / 480 | 466 / 480 |
| dorian | 480 / 480 | 480 / 480 |
| phrygian | 468 / 480 | 462 / 480 |
| lydian | 474 / 480 | 470 / 480 |
| mixolydian | 480 / 480 | 476 / 480 |
| aeolian | 474 / 480 | 470 / 480 |
| locrian | 462 / 480 | 459 / 480 |

The frozen offline search inspection found fewer than three distinct bounded patches for nine inputs. These cases remain in the full schedule and denominator. Capacity-conditioned counts below describe this limitation; they do not replace the complete-schedule result.

| Search capacity | Open passed / scheduled | Spark 1.3 passed / scheduled |
|---|---:|---:|
| at least three | 4186 / 4186 | 4144 / 4186 |
| fewer than three | 0 / 54 | 0 / 54 |

## Repeated choices and failures

- baseten: 671/680 passages passed all scheduled repeats; 114 returned the same musical offer set on every scheduled repeat. Mean per-passage successful-pair Jaccard overlap: 0.7050240105977811.
- meta: 635/680 passages passed all scheduled repeats; 111 returned the same musical offer set on every scheduled repeat. Mean per-passage successful-pair Jaccard overlap: 0.7234497196792279.

Recorded failed, cancelled, or non-passing started executions: **150**. Unstarted executions: **0**. All are retained. No failed result was replaced by a paid rerun.

Failure categories, each scheduled row, paired outcomes, request IDs, usage totals and raw-artifact hashes are in [the numeric report](completion-summary.json). Original full requests, provider replies and tool feedback are in the linked compressed JSON trace files. The gzip headers contain no work timestamp.

Combined budget accounting: **$81.25503600**, against the **$120.00** combined cap. Returned token usage is multiplied by the configured rates; unknown usage retains its reservation. These are nominal cost estimates, not confirmed charges, paid invoices or measured credit deductions. Provider credits, sponsorships or discounts are not reconciled here. Meta and Baseten usage is recorded separately.

Hackathon support guidance supplied by the participant places the Baseten key in a separate hackathon workspace with $100 credit expiring November 9 and no provider-side usage or balance view. Personal-dashboard figures therefore do not measure this key. See [credit attribution](README.md#hackathon-credit-attribution); local token accounting does not establish the remaining credit.

## Interpretation and limits

Muse requests searches; the unchanged tools construct candidates and the author's F1 Music Transformer scores their surrounding context. Muse chooses its final three from saved search feedback. The user chooses what to apply in the product. The evaluator stops at the returned offer.

The data are authored engineering fixtures using related templates. The 40 regression passages include a deliberately targeted earlier timeout and are post-hoc evidence. Input-level and repeat-level denominators remain separate. This is not a population estimate over independent songs.

Two evaluation processes per provider, existing adapter differences, local contention and uncontrolled provider caching affect time and cost. These are observed execution measurements, not isolated model speed or musical-quality rankings. Automatic validity, candidate overlap and F1 scores do not establish listening preference. Listening research is planned separately for a paper.

The campaign does not exercise browser interaction, hosted HTTP admission, user application, MIDI export or DAW playback. Full requests reach 512 bars; the existing agent/scorer window remains at most 24 bars. Product code and settings were not changed to improve results.

[Frozen protocol and inputs](README.md) · [Offline completion verifier](tools/completion_report.py) · [Previous 880-run study](../reharmonize_agent_eval/extended-summary.md)
