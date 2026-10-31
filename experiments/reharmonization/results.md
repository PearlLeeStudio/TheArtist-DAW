# Reharmonization comparison results

This is the original **F4** batch. The [F2/F3 follow-up](f2-f3-rank-results.md)
and [combined Korean interpretation](../../docs/reharmonization-evaluation.md)
keep the subsequent changed-model results separate.

40 passages across 16 tune groups; 480 candidate positions, 225 distinct versions within passages.

**There is no clear quality winner among Meta, Hybrid 1 and Hybrid 2.** Meta has
the highest mean under the automated judge, but its paired intervals against both
hybrids include zero. A second hybrid pass adds little average benefit and almost
doubles selection cost and latency. This supports withholding automatic second
passes; it does not establish that hybrid scoring beats Meta-only selection.

The fixed [protocol](README.md), [numeric results](summary.json) and
[210-call usage audit](calls.json) are available alongside this report. The audit
includes the separate two-passage pilot: $0.11096150, with one output-limited
selection and one output-limited judgment. Main cost is $2.35408405; total ledger
cost is **$2.46504555**, with no outstanding reservation. Downloaded MIDI and the
detailed 40-passage candidate HTML remain local in `.cache/`.

Tune-balanced means. Blind scores are automated 0–4 ratings, not listening results.

| Condition | Completed | Judged twice | Blind mean | First choice | Best of 3 | Worst of 3 | Seconds | USD per passage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local | 40/40 | 40 | 2.464 | 2.607 | 3.202 | 1.698 | 0.132 | 0.000 |
| meta | 40/40 | 40 | 2.671 | 2.803 | 3.277 | 1.952 | 7.503 | 0.011 |
| hybrid1 | 40/40 | 40 | 2.624 | 2.734 | 3.294 | 1.818 | 7.293 | 0.011 |
| hybrid2 | 40/40 | 40 | 2.649 | 2.779 | 3.298 | 1.871 | 13.871 | 0.022 |

Hybrid 2 includes its shared Hybrid 1 cost and time. Actual batch cost counts that pass once.

| Paired difference (left − right) | Mean | 95% tune bootstrap interval | Tunes |
| --- | ---: | --- | ---: |
| local-meta | -0.208 | [-0.379, -0.042] | 16 |
| local-hybrid1 | -0.160 | [-0.302, -0.032] | 16 |
| local-hybrid2 | -0.186 | [-0.345, -0.034] | 16 |
| meta-hybrid1 | 0.048 | [-0.026, 0.131] | 16 |
| meta-hybrid2 | 0.022 | [-0.069, 0.108] | 16 |
| hybrid1-hybrid2 | -0.026 | [-0.134, 0.044] | 16 |

Actual batch cost: $2.354084.

Six exploratory pairwise intervals; no multiplicity correction. They quantify this automated judge, not human preference.

## Rubric and presentation stability

| Condition | Continuity | Melody fit | Useful change | Retained identity | Order 1 | Order 2 | Mean absolute order difference |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local | 2.734 | 2.632 | 1.752 | 2.736 | 2.482 | 2.445 | 0.328 |
| meta | 2.931 | 2.688 | 2.214 | 2.854 | 2.690 | 2.653 | 0.405 |
| hybrid1 | 2.922 | 2.583 | 2.170 | 2.819 | 2.627 | 2.621 | 0.378 |
| hybrid2 | 2.946 | 2.634 | 2.177 | 2.840 | 2.656 | 2.642 | 0.378 |

Order differences also include model sampling variation; this is not a pure causal estimate of position bias.

## Descriptive secondary measurements

| Condition | Strict melody support Δ | Pitch distance Δ | Bass motion Δ | Performance profile cosine Δ | F1 log likelihood | Changed slots |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| local | -0.017 | -0.037 | -0.368 | 0.002 | -4.629 | 1.097 |
| meta | -0.026 | -0.023 | -0.569 | 0.003 | -5.067 | 1.181 |
| hybrid1 | -0.045 | -0.015 | -0.417 | 0.002 | -5.030 | 1.122 |
| hybrid2 | -0.035 | -0.012 | -0.421 | 0.002 | -5.031 | 1.111 |

Δ is relative to the unchanged original. Lower motion means closer pitch classes/bass, not necessarily better harmony.
Strict support counts chord tones only and can reward denser chords; a melody tension is not automatically an error.
Performance-profile similarity is whole-excerpt descriptive evidence; the performance MIDI is not an expert chord answer.
F1 log likelihood is higher when less negative. F1 and selecting F4 share ancestry; this is not fully independent validation.

## Completion and controls

Hybrid 2 changed the candidate set in 5/40 passages; changed the ordered list in 7/40.
Control fit (excluding useful change): original 3.900, semitone perturbation 0.996; original higher in 40/40 passages. A perturbation is not guaranteed to be musically wrong.

Preparation failures: 0; generation failures/blocked arms: 0; judgment failures: 0.

Meta is both a selector and judge. No frontend choice follows automatically from these scores.

## What the differences mean

1. **Meta's selection contribution is more evident than an extra review pass.**
   The local arm's useful-change score is 1.752, versus 2.214 for Meta and
   2.170–2.177 for the hybrids. Meta's average advantage over local is 0.208/4
   in this judge. These are exploratory, same-family model judgments, with no
   listening or independent human preference evidence.
   Local takes the first three by F4 likelihood without a separate diversity
   reranker, while Meta is explicitly asked for contrasting useful alternatives.
   Some difference may reflect those selection objectives; a deterministic
   diversity-aware local baseline has not been measured here.
2. **Hybrid 2 mostly repeats Hybrid 1.** Candidate sets change in only 5/40
   passages, and the ordered lists change in 7/40. Of those five set changes,
   two improve the automated mean and three worsen it. Both improvements are
   passages from *Body And Soul* (`x_472`: 2.125→2.958; `x_473`: 2.375→3.083).
   The average gain is therefore concentrated in one tune, and its paired
   interval against Hybrid 1 crosses zero. This review receives no new musical
   evidence, only the first pass and its reasons.
3. **Three candidates still need comparison.** As a post-hoc descriptive check,
   the first-ranked candidate ties or beats the other two in only 20/40 local,
   17/40 Meta, 18/40 Hybrid 1 and 20/40 Hybrid 2 passages. At least one candidate
   averages below 2/4 in 28, 20, 24 and 23 passages respectively. Best-of-three
   scores assume an oracle choice; do not claim those scores as automatic output
   quality or remove the user's A/B/C choice on their basis.
4. **Melody is the most concrete missing input to test next.** Every selector
   receives chords and context, while the judge additionally receives melody
   profiles. Strict melody chord-tone support falls by 1.7–4.5 percentage points
   on average across all four methods. This is not a dissonance/error rate, but
   it identifies a constraint the current selection path cannot directly use.
   Feeding imported melody evidence into candidate screening and selection is
   a proposed next experiment, not a demonstrated improvement.
5. **Explanations require factual checks.** In the pilot `x_12`, a hybrid reason
   attributes four common tones to the preceding chord transition. Direct
   pitch-class intersection gives two for that transition; four applies to the
   selected original chord and its replacement. In main `x_104`, reasons call
   B-flat minor “iv” without specifying a local key, although its root is scale
   degree V of the supplied E-flat key. These spot checks are not a measured
   explanation-error rate. Computed before/after facts should remain explicit
   instead of treating fluent model reasons as verified theory.

For the frontend decision, keeping the current one-pass hybrid and persistent
three-candidate comparison is a defensible continuity choice, **not a proven
quality advantage over Meta-only selection**. There is no evidence here for
making two passes the default or exposing all four experimental conditions as
four user-facing modes. Product UI changes are deferred to the user's decision.

The comparison concerns selection from an identical 11–18-candidate mathematical
pool, using F4 as the local selector. It does not test unrestricted regeneration,
all 18 checkpoints, expert reharmonization ground-truth matching, full-score
melodic phrasing, or the production agent's dynamic tool-loop latency.

Validation: backend suite `Ran 602 tests ... OK`; eight focused experiment tests
pass after report changes; frontend build and lint and `import app.main: ok`
pass. The existing bundle-size warning remains. Rebuilding the dataset reproduces
the frozen bytes exactly. The local HTML was opened in Chrome, its four-by-three
table and changed-chord highlighting inspected; this is not an audio check.
