# Recommendation ranks and eight-position coverage

**F4 reference only.** The original batch covers 40 passages/16 tune groups.
The repeat was interrupted after 13 fully recorded passages/13 tune groups when
the local-checkpoint choice changed. Its repeat and combined tables are partial,
exploratory evidence; the combined table covers only those same 13 passages
(26 case-runs), not the full 40. F2 and F3 are the requested follow-up models.

Scores are blinded automated ratings on 0–4. Positions retain the selector’s recommendation order.
Means average repeats within passage, then passages within tune. Intervals bootstrap tune groups (5,000 draws).
Signed gaps can be negative; candidates have not been reordered using the judge. Intervals are exploratory, without multiplicity correction.

## Original

| Method | Rank 1 | Rank 2 | Rank 3 | 1−2 | 95% interval | 2−3 | 95% interval |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| local | 2.607 | 2.366 | 2.418 | 0.241 | [-0.202, 0.669] | -0.052 | [-0.449, 0.314] |
| meta | 2.803 | 2.669 | 2.542 | 0.134 | [-0.266, 0.510] | 0.128 | [-0.280, 0.540] |
| hybrid1 | 2.734 | 2.909 | 2.228 | -0.174 | [-0.483, 0.134] | 0.681 | [0.279, 1.082] |
| hybrid2 | 2.779 | 2.875 | 2.294 | -0.096 | [-0.419, 0.214] | 0.581 | [0.227, 0.936] |

| Method | 1 > / = / < 2 (passages) | 2 > / = / < 3 (passages) | Best-of-3 missed by first two | Oracle score loss |
| --- | --- | --- | ---: | ---: |
| local | 23 / 2 / 15 | 16 / 4 / 20 | 8/40 | 0.132 |
| meta | 19 / 2 / 19 | 19 / 4 / 17 | 9/40 | 0.089 |
| hybrid1 | 16 / 4 / 20 | 30 / 1 / 9 | 5/40 | 0.095 |
| hybrid2 | 18 / 4 / 18 | 29 / 1 / 10 | 5/40 | 0.081 |

Eight selected positions contain 3.927 distinct musical versions on average (range 2–5), versus 5.688 for all 12 positions.
The eight-position union misses the 12-position oracle best in 3/40 case-runs (3 distinct passages). Mean oracle score loss: 0.013.
Coverage means retaining the highest automated score, including ties; it does not measure a listener’s chosen alternative.

## Repeat

| Method | Rank 1 | Rank 2 | Rank 3 | 1−2 | 95% interval | 2−3 | 95% interval |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| local | 2.587 | 2.048 | 2.558 | 0.538 | [-0.356, 1.365] | -0.510 | [-1.115, 0.183] |
| meta | 2.817 | 2.933 | 2.365 | -0.115 | [-0.577, 0.356] | 0.567 | [-0.029, 1.173] |
| hybrid1 | 2.808 | 2.798 | 2.606 | 0.010 | [-0.423, 0.413] | 0.192 | [-0.298, 0.721] |
| hybrid2 | 2.779 | 2.894 | 2.413 | -0.115 | [-0.538, 0.279] | 0.481 | [-0.048, 1.077] |

| Method | 1 > / = / < 2 (passages) | 2 > / = / < 3 (passages) | Best-of-3 missed by first two | Oracle score loss |
| --- | --- | --- | ---: | ---: |
| local | 10 / 0 / 3 | 4 / 0 / 9 | 3/13 | 0.125 |
| meta | 6 / 0 / 7 | 8 / 1 / 4 | 4/13 | 0.125 |
| hybrid1 | 6 / 0 / 7 | 5 / 1 / 7 | 3/13 | 0.144 |
| hybrid2 | 5 / 0 / 8 | 8 / 1 / 4 | 2/13 | 0.115 |

Eight selected positions contain 3.923 distinct musical versions on average (range 3–5), versus 6.077 for all 12 positions.
The eight-position union misses the 12-position oracle best in 1/13 case-runs (1 distinct passages). Mean oracle score loss: 0.029.
Coverage means retaining the highest automated score, including ties; it does not measure a listener’s chosen alternative.

## Combined

| Method | Rank 1 | Rank 2 | Rank 3 | 1−2 | 95% interval | 2−3 | 95% interval |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| local | 2.606 | 2.082 | 2.567 | 0.524 | [-0.380, 1.346] | -0.486 | [-1.139, 0.255] |
| meta | 2.880 | 2.885 | 2.567 | -0.005 | [-0.462, 0.418] | 0.317 | [-0.087, 0.712] |
| hybrid1 | 2.832 | 2.894 | 2.476 | -0.062 | [-0.500, 0.356] | 0.418 | [-0.139, 0.966] |
| hybrid2 | 2.817 | 2.933 | 2.389 | -0.115 | [-0.572, 0.322] | 0.543 | [-0.058, 1.173] |

| Method | 1 > / = / < 2 (passages) | 2 > / = / < 3 (passages) | Best-of-3 missed by first two | Oracle score loss |
| --- | --- | --- | ---: | ---: |
| local | 9 / 1 / 3 | 4 / 0 / 9 | 3/13 | 0.106 |
| meta | 8 / 1 / 4 | 8 / 0 / 5 | 4/13 | 0.067 |
| hybrid1 | 6 / 0 / 7 | 8 / 0 / 5 | 3/13 | 0.130 |
| hybrid2 | 6 / 0 / 7 | 9 / 0 / 4 | 2/13 | 0.115 |

Eight selected positions contain 4.000 distinct musical versions on average (range 3–5), versus 5.962 for all 12 positions.
The eight-position union misses the 12-position oracle best in 1/26 case-runs (1 distinct passages). Mean oracle score loss: 0.014.
Coverage means retaining the highest automated score, including ties; it does not measure a listener’s chosen alternative.

## Selection repeatability

| Method | Same first | Same top-two set | Top-two overlap | Same top-three set | Same ordered three |
| --- | ---: | ---: | ---: | ---: | ---: |
| local | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| meta | 30.8% | 38.5% | 65.4% | 15.4% | 0.0% |
| hybrid1 | 69.2% | 76.9% | 88.5% | 53.8% | 38.5% |
| hybrid2 | 84.6% | 69.2% | 84.6% | 53.8% | 46.2% |

Mean absolute score difference for shared versions across runs: 0.282/4 over 68 shared passage-version pairs. This is judging variation, separate from changes in selection.

Meta is both selector and judge. The material is chord context plus coarse melody profiles, with no listening or expert preference labels.
A repeat on the same tunes is not an independent new-song test. No UI decision or new genre claim follows automatically.
