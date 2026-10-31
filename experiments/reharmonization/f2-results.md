# Reharmonization comparison results

Local/hybrid checkpoint: `ft_f2`. Meta-only receives no checkpoint score.

40 passages across 16 tune groups; 480 candidate positions, 216 distinct versions within passages.

Tune-balanced means. Blind scores are automated 0–4 ratings, not listening results.

| Condition | Completed | Judged twice | Blind mean | First choice | Best of 3 | Worst of 3 | Seconds | USD per passage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local | 40/40 | 40 | 2.516 | 2.625 | 3.250 | 1.733 | 0.221 | 0.000 |
| meta | 40/40 | 40 | 2.589 | 2.820 | 3.206 | 1.888 | 7.007 | 0.010 |
| hybrid1 | 40/40 | 40 | 2.688 | 2.789 | 3.340 | 1.993 | 7.602 | 0.011 |
| hybrid2 | 40/40 | 40 | 2.718 | 2.818 | 3.353 | 2.064 | 14.084 | 0.022 |

Hybrid 2 includes its shared Hybrid 1 cost and time. Actual batch cost counts that pass once.

| Paired difference (left − right) | Mean | 95% tune bootstrap interval | Tunes |
| --- | ---: | --- | ---: |
| local-meta | -0.073 | [-0.209, 0.060] | 16 |
| local-hybrid1 | -0.172 | [-0.322, -0.018] | 16 |
| local-hybrid2 | -0.202 | [-0.349, -0.045] | 16 |
| meta-hybrid1 | -0.099 | [-0.184, -0.000] | 16 |
| meta-hybrid2 | -0.129 | [-0.215, -0.049] | 16 |
| hybrid1-hybrid2 | -0.030 | [-0.088, 0.012] | 16 |

Actual batch cost: $2.291709.

Six exploratory pairwise intervals; no multiplicity correction. They quantify this automated judge, not human preference.

## Rubric and presentation stability

| Condition | Continuity | Melody fit | Useful change | Retained identity | Order 1 | Order 2 | Mean absolute order difference |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local | 2.793 | 2.705 | 1.783 | 2.781 | 2.533 | 2.498 | 0.356 |
| meta | 2.880 | 2.509 | 2.085 | 2.882 | 2.608 | 2.570 | 0.367 |
| hybrid1 | 2.967 | 2.679 | 2.142 | 2.962 | 2.693 | 2.682 | 0.365 |
| hybrid2 | 3.019 | 2.700 | 2.139 | 3.014 | 2.719 | 2.717 | 0.373 |

Order differences also include model sampling variation; this is not a pure causal estimate of position bias.

## Descriptive secondary measurements

| Condition | Strict melody support Δ | Pitch distance Δ | Bass motion Δ | Performance profile cosine Δ | F1 log likelihood | Changed slots |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| local | 0.002 | -0.044 | -0.347 | 0.001 | -4.646 | 1.118 |
| meta | -0.047 | -0.015 | -0.551 | 0.003 | -5.112 | 1.149 |
| hybrid1 | -0.024 | -0.022 | -0.468 | 0.003 | -5.002 | 1.170 |
| hybrid2 | -0.024 | -0.019 | -0.468 | 0.004 | -4.988 | 1.139 |

Δ is relative to the unchanged original. Lower motion means closer pitch classes/bass, not necessarily better harmony.
Strict support counts chord tones only and can reward denser chords; a melody tension is not automatically an error.
Performance-profile similarity is whole-excerpt descriptive evidence; the performance MIDI is not an expert chord answer.
F1 log likelihood is higher when less negative. F1 and the selecting checkpoint share ancestry; this is not fully independent validation.

## Completion and controls

Hybrid 2 changed the candidate set in 4/40 passages; changed the ordered list in 5/40.
Control fit (excluding useful change): original 3.921, semitone perturbation 0.950; original higher in 40/40 passages. A perturbation is not guaranteed to be musically wrong.

Preparation failures: 0; generation failures/blocked arms: 0; judgment failures: 0.

Meta is both a selector and judge. No frontend choice follows automatically from these scores.
