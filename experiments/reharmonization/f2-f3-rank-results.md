# Recommendation ranks and eight-position coverage

**Both requested batches finished:** 40 paired passages per checkpoint, 200 successful calls each.
No clear F2-versus-F3 winner is established by first-two means: all paired intervals cross zero.
The F4 hybrid rank-2 advantage over rank 3 does not clearly replicate with F2 or F3.
Dropping each method's third choice retains the all-12 oracle best in 35/40 passages per model;
first collecting all three and then deduplicating leaves at most eight versions in every tested passage.
Thus an eight-card ceiling can retain all evaluated options here without another API call.
This is an observed property of these pools, not a future-input guarantee or a UI change.

Scores are blinded automated ratings on 0–4. Positions retain the selector’s recommendation order.
Means average repeats within passage, then passages within tune. Intervals bootstrap tune groups (5,000 draws).
Signed gaps can be negative; candidates have not been reordered using the judge. Intervals are exploratory, without multiplicity correction.

## F2

40 case-runs across 40 passages and 16 tune groups.

| Method | Rank 1 | Rank 2 | Rank 3 | 1−2 | 95% interval | 2−3 | 95% interval |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| local | 2.625 | 2.341 | 2.581 | 0.284 | [-0.118, 0.668] | -0.240 | [-0.523, 0.033] |
| meta | 2.820 | 2.712 | 2.234 | 0.108 | [-0.206, 0.424] | 0.478 | [0.230, 0.745] |
| hybrid1 | 2.789 | 2.651 | 2.622 | 0.138 | [-0.245, 0.497] | 0.029 | [-0.342, 0.384] |
| hybrid2 | 2.818 | 2.695 | 2.641 | 0.122 | [-0.234, 0.453] | 0.055 | [-0.255, 0.380] |

| Method | 1 > / = / < 2 (passages) | 2 > / = / < 3 (passages) | Best-of-3 missed by first two | Oracle score loss |
| --- | --- | --- | ---: | ---: |
| local | 24 / 1 / 15 | 13 / 5 / 22 | 11/40 | 0.194 |
| meta | 21 / 3 / 16 | 28 / 1 / 11 | 3/40 | 0.036 |
| hybrid1 | 18 / 2 / 20 | 19 / 0 / 21 | 10/40 | 0.164 |
| hybrid2 | 19 / 2 / 19 | 19 / 0 / 21 | 9/40 | 0.174 |

Eight selected positions contain 4.021 distinct musical versions on average (range 2–6), versus 5.500 for all 12 positions.
The eight-position union misses the 12-position oracle best in 5/40 case-runs (5 distinct passages). Mean oracle score loss: 0.057.
Coverage means retaining the highest automated score, including ties; it does not measure a listener’s chosen alternative.

Deduplicating all 12 positions first leaves 4–8 versions. All of them fit within eight cards in 40/40 case-runs. This retains every evaluated third choice in those cases, without another model call; it is not a guarantee for future inputs.

## F3

40 case-runs across 40 passages and 16 tune groups.

| Method | Rank 1 | Rank 2 | Rank 3 | 1−2 | 95% interval | 2−3 | 95% interval |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| local | 2.581 | 2.378 | 2.615 | 0.203 | [-0.271, 0.603] | -0.237 | [-0.589, 0.105] |
| meta | 2.783 | 2.680 | 2.232 | 0.103 | [-0.310, 0.479] | 0.448 | [0.009, 0.888] |
| hybrid1 | 2.896 | 2.647 | 2.389 | 0.249 | [-0.089, 0.565] | 0.258 | [-0.224, 0.720] |
| hybrid2 | 2.915 | 2.717 | 2.354 | 0.198 | [-0.168, 0.530] | 0.363 | [-0.117, 0.835] |

| Method | 1 > / = / < 2 (passages) | 2 > / = / < 3 (passages) | Best-of-3 missed by first two | Oracle score loss |
| --- | --- | --- | ---: | ---: |
| local | 24 / 1 / 15 | 12 / 5 / 23 | 11/40 | 0.164 |
| meta | 20 / 4 / 16 | 25 / 2 / 13 | 7/40 | 0.062 |
| hybrid1 | 23 / 3 / 14 | 23 / 2 / 15 | 9/40 | 0.164 |
| hybrid2 | 23 / 2 / 15 | 24 / 2 / 14 | 8/40 | 0.138 |

Eight selected positions contain 3.896 distinct musical versions on average (range 2–6), versus 5.469 for all 12 positions.
The eight-position union misses the 12-position oracle best in 5/40 case-runs (5 distinct passages). Mean oracle score loss: 0.090.
Coverage means retaining the highest automated score, including ties; it does not measure a listener’s chosen alternative.

Deduplicating all 12 positions first leaves 3–8 versions. All of them fit within eight cards in 40/40 case-runs. This retains every evaluated third choice in those cases, without another model call; it is not a guarantee for future inputs.

## Paired difference: F2 minus F3

| Method | First-two mean difference | 95% tune interval | First-choice difference | All-three mean difference |
| --- | ---: | --- | ---: | ---: |
| local | 0.004 | [-0.118, 0.130] | 0.044 | -0.009 |
| meta | 0.035 | [-0.163, 0.237] | 0.038 | 0.024 |
| hybrid1 | -0.051 | [-0.221, 0.135] | -0.107 | 0.043 |
| hybrid2 | -0.060 | [-0.212, 0.099] | -0.098 | 0.056 |

Meta-only receives no local checkpoint score and identical inputs in both batches. Its difference reflects selection/judgment sampling, not a checkpoint effect.
The other differences also include run variation. These model batches are paired observations of the same passages, not independent new songs.

Meta is both selector and judge. The material is chord context plus coarse melody profiles, with no listening or expert preference labels.
A repeat on the same tunes is not an independent new-song test. No UI decision or new genre claim follows automatically.
