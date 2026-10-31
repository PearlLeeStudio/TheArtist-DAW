# Reharmonization comparison results

Local/hybrid checkpoint: `ft_f3`. Meta-only receives no checkpoint score.

40 passages across 16 tune groups; 480 candidate positions, 214 distinct versions within passages.

Tune-balanced means. Blind scores are automated 0–4 ratings, not listening results.

| Condition | Completed | Judged twice | Blind mean | First choice | Best of 3 | Worst of 3 | Seconds | USD per passage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local | 40/40 | 40 | 2.524 | 2.581 | 3.227 | 1.730 | 0.219 | 0.000 |
| meta | 40/40 | 40 | 2.565 | 2.783 | 3.197 | 1.837 | 7.398 | 0.010 |
| hybrid1 | 40/40 | 40 | 2.644 | 2.896 | 3.306 | 1.896 | 7.724 | 0.012 |
| hybrid2 | 40/40 | 40 | 2.662 | 2.915 | 3.320 | 1.921 | 14.610 | 0.023 |

Hybrid 2 includes its shared Hybrid 1 cost and time. Actual batch cost counts that pass once.

| Paired difference (left − right) | Mean | 95% tune bootstrap interval | Tunes |
| --- | ---: | --- | ---: |
| local-meta | -0.040 | [-0.159, 0.084] | 16 |
| local-hybrid1 | -0.120 | [-0.224, -0.024] | 16 |
| local-hybrid2 | -0.138 | [-0.241, -0.043] | 16 |
| meta-hybrid1 | -0.079 | [-0.146, -0.015] | 16 |
| meta-hybrid2 | -0.098 | [-0.174, -0.034] | 16 |
| hybrid1-hybrid2 | -0.018 | [-0.053, 0.020] | 16 |

Actual batch cost: $2.301017.

Six exploratory pairwise intervals; no multiplicity correction. They quantify this automated judge, not human preference.

## Rubric and presentation stability

| Condition | Continuity | Melody fit | Useful change | Retained identity | Order 1 | Order 2 | Mean absolute order difference |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local | 2.861 | 2.668 | 1.724 | 2.844 | 2.536 | 2.512 | 0.328 |
| meta | 2.896 | 2.533 | 2.024 | 2.806 | 2.571 | 2.558 | 0.407 |
| hybrid1 | 2.941 | 2.660 | 2.085 | 2.891 | 2.671 | 2.617 | 0.372 |
| hybrid2 | 2.976 | 2.658 | 2.099 | 2.917 | 2.687 | 2.638 | 0.356 |

Order differences also include model sampling variation; this is not a pure causal estimate of position bias.

## Descriptive secondary measurements

| Condition | Strict melody support Δ | Pitch distance Δ | Bass motion Δ | Performance profile cosine Δ | F1 log likelihood | Changed slots |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| local | -0.016 | -0.048 | -0.359 | 0.002 | -4.643 | 1.101 |
| meta | -0.038 | -0.016 | -0.558 | 0.004 | -5.082 | 1.146 |
| hybrid1 | -0.037 | -0.017 | -0.419 | 0.003 | -4.958 | 1.073 |
| hybrid2 | -0.044 | -0.020 | -0.477 | 0.002 | -4.963 | 1.087 |

Δ is relative to the unchanged original. Lower motion means closer pitch classes/bass, not necessarily better harmony.
Strict support counts chord tones only and can reward denser chords; a melody tension is not automatically an error.
Performance-profile similarity is whole-excerpt descriptive evidence; the performance MIDI is not an expert chord answer.
F1 log likelihood is higher when less negative. F1 and the selecting checkpoint share ancestry; this is not fully independent validation.

## Completion and controls

Hybrid 2 changed the candidate set in 5/40 passages; changed the ordered list in 6/40.
Control fit (excluding useful change): original 3.925, semitone perturbation 0.958; original higher in 40/40 passages. A perturbation is not guaranteed to be musically wrong.

Preparation failures: 0; generation failures/blocked arms: 0; judgment failures: 0.

Meta is both a selector and judge. No frontend choice follows automatically from these scores.
