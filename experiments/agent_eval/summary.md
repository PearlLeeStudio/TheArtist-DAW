# Planner evaluation (U3): Complete the form, Muse Spark against the genre-default form

20 fixed requests (10 new songs, 6 completions, 4 tight completions), run on 2026-10-29
with real Muse Spark 1.3 calls through the product's planner service and the author's
chord model. **Before** = the `rules` planner (genre-default form, no Meta call), **after**
= the `meta` planner at plan effort medium. The effort comparison reruns a fixed
6-request subset at low, medium and high. Every number below comes from the result
files in `results/`, which keep each run's trace and request ids.

## What the numbers show

- **Every run completed.** 20/20 Meta runs finished plan → validate → generate →
  judge, at $0.0159 per run on average (plan alone $0.0102) and 18.1 s median, 25.0 s
  p95. A first evaluation the same day completed only 14/20: six judgments ran out of
  their 1024-token output budget (reasoning tokens count toward it). That was fixed in
  `da5d929` (judgment 4096, plan 8192 tokens) before this run.
- **The validator never had to send a plan back.** First-pass validity was 100% at
  every effort, and 0 revisions were needed, so the revision loop is exercised only by
  the tests with a fake model, not by these real runs. All plan citations (7.6 per
  plan, a bar and its Roman numeral) matched the sketch. The four "tight" requests were
  not tight enough to make Muse Spark fail.
- **What Meta adds over the genre default:** cited reasons for each section, more
  varied forms (3.5 distinct section types per plan against 2.8), and the
  observe-then-act judgment, which sent at least one section back for regeneration in
  9 of 20 runs (45%). Structural validity does not separate the two: the rules planner
  is built to satisfy the same validator.
- **Effort:** low was the cheapest and fastest ($0.0117 per run, plan 5.1 s median) and
  just as valid on this subset; high cost 1.8× low and took 2.6× as long without a
  validity gain. The product keeps medium for the plan and low for revisions and
  judgments.

## What they do not show

- **Musical quality.** No listening test was run; "valid" means the form passes the
  code validator, not that the music is better than the genre default.
- **Generality.** N = 20 self-written requests (6 for the effort comparison), one model,
  one day. The judgment's analyzer facts (out-of-key share, repetition, empty slots)
  are coarse.

The tables below are the output of `agent/plan_and_generate.py --report`.

## Invocations

| run | N | first-pass valid | valid after revision | mean revisions | completed | regenerate rate | tight: first-pass / final | cites / plan | cite errors (first pass) | distinct types / plan | plan p50 / p95 (s) | total p50 / p95 (s) | USD / run | plan USD / run | USD total | failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `rules.json` (rules) | 20 | 20/20 (100%) | 20/20 (100%) | 0.00 | 20/20 (100%) | 0/20 (0%) | 4/4 (100%) / 4/4 (100%) | 0.0 | 0/10 (0%) | 2.8 | 0.0 / 0.0 | 2.4 / 7.7 | 0.0000 | 0.0000 | 0.0000 | none |
| `meta-low.json` (meta, plan effort low) | 6 | 6/6 (100%) | 6/6 (100%) | 0.00 | 6/6 (100%) | 3/6 (50%) | 3/3 (100%) / 3/3 (100%) | 7.5 | 0/4 (0%) | 2.8 | 5.1 / 7.1 | 13.7 / 18.3 | 0.0117 | 0.0063 | 0.0700 | none |
| `meta-medium.json` (meta, plan effort medium) | 20 | 20/20 (100%) | 20/20 (100%) | 0.00 | 20/20 (100%) | 9/20 (45%) | 4/4 (100%) / 4/4 (100%) | 7.6 | 0/10 (0%) | 3.5 | 8.4 / 13.6 | 18.1 / 25.0 | 0.0159 | 0.0102 | 0.3181 | none |
| `meta-high.json` (meta, plan effort high) | 6 | 6/6 (100%) | 6/6 (100%) | 0.00 | 6/6 (100%) | 2/6 (33%) | 3/3 (100%) / 3/3 (100%) | 7.0 | 0/4 (0%) | 2.8 | 13.5 / 17.4 | 20.9 / 27.1 | 0.0216 | 0.0157 | 0.1297 | none |

- `rules.json`: 2026-10-29T06:01:19+00:00, 20 of 20 requests; clients default: meta muse-spark-1.3; judge: meta muse-spark-1.3; efforts plan medium / revise low / judge low; ledger before default $0.2418 of $25.00; judge shares the default ledger, after default $0.2418 of $25.00; judge shares the default ledger
- `meta-low.json`: 2026-10-29T09:25:57+00:00, 6 of 6 requests; clients default: meta muse-spark-1.3; judge: meta muse-spark-1.3; efforts plan low / revise low / judge low; ledger before default $2.1624 of $25.00; judge shares the default ledger, after default $2.2324 of $25.00; judge shares the default ledger
- `meta-medium.json`: 2026-10-29T09:19:51+00:00, 20 of 20 requests; clients default: meta muse-spark-1.3; judge: meta muse-spark-1.3; efforts plan medium / revise low / judge low; ledger before default $1.8442 of $25.00; judge shares the default ledger, after default $2.1624 of $25.00; judge shares the default ledger
- `meta-high.json`: 2026-10-29T09:27:17+00:00, 6 of 6 requests; clients default: meta muse-spark-1.3; judge: meta muse-spark-1.3; efforts plan high / revise low / judge low; ledger before default $2.2324 of $25.00; judge shares the default ledger, after default $2.3621 of $25.00; judge shares the default ledger

## Plan effort on the fixed subset (new_pop_32, new_jazz_64, complete_hiphop_amin_8bar_32, tight_blues_e_12bar_48_outro, tight_folk_g_14bar_16_outro, tight_pop_c_10bar_32_high)

| run | N | first-pass valid | valid after revision | mean revisions | completed | regenerate rate | tight: first-pass / final | cites / plan | cite errors (first pass) | distinct types / plan | plan p50 / p95 (s) | total p50 / p95 (s) | USD / run | plan USD / run | USD total | failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| plan effort low | 6 | 6/6 (100%) | 6/6 (100%) | 0.00 | 6/6 (100%) | 3/6 (50%) | 3/3 (100%) / 3/3 (100%) | 7.5 | 0/4 (0%) | 2.8 | 5.1 / 7.1 | 13.7 / 18.3 | 0.0117 | 0.0063 | 0.0700 | none |
| plan effort medium | 6 | 6/6 (100%) | 6/6 (100%) | 0.00 | 6/6 (100%) | 3/6 (50%) | 3/3 (100%) / 3/3 (100%) | 8.0 | 0/4 (0%) | 3.2 | 7.5 / 11.9 | 15.0 / 21.1 | 0.0148 | 0.0098 | 0.0889 | none |
| plan effort high | 6 | 6/6 (100%) | 6/6 (100%) | 0.00 | 6/6 (100%) | 2/6 (33%) | 3/3 (100%) / 3/3 (100%) | 7.0 | 0/4 (0%) | 2.8 | 13.5 / 17.4 | 20.9 / 27.1 | 0.0216 | 0.0157 | 0.1297 | none |

## Before / after on the full set

| run | N | first-pass valid | valid after revision | mean revisions | completed | regenerate rate | tight: first-pass / final | cites / plan | cite errors (first pass) | distinct types / plan | plan p50 / p95 (s) | total p50 / p95 (s) | USD / run | plan USD / run | USD total | failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| rules (before) | 20 | 20/20 (100%) | 20/20 (100%) | 0.00 | 20/20 (100%) | 0/20 (0%) | 4/4 (100%) / 4/4 (100%) | 0.0 | 0/10 (0%) | 2.8 | 0.0 / 0.0 | 2.4 / 7.7 | 0.0000 | 0.0000 | 0.0000 | none |
| meta, plan effort medium (after) | 20 | 20/20 (100%) | 20/20 (100%) | 0.00 | 20/20 (100%) | 9/20 (45%) | 4/4 (100%) / 4/4 (100%) | 7.6 | 0/10 (0%) | 3.5 | 8.4 / 13.6 | 18.1 / 25.0 | 0.0159 | 0.0102 | 0.3181 | none |

## Per request: `rules.json`

| request | kind | first pass | revisions | plan | judge | regenerated | plan (s) | total (s) | USD | status |
|---|---|---|---:|---|---|---:|---:|---:|---:|---|
| complete_bossa_f_16bar_64 | complete | ok | 0 | a_section 8, a_section 8, b_section 8, a_section 8, a_section 8, a_section 4, outro 4 | - | 0 | 0.0 | 6.1 | 0.0000 | ok |
| complete_country_g_16bar_32 | complete | ok | 0 | verse 8, chorus 4, outro 4 | - | 0 | 0.0 | 1.4 | 0.0000 | ok |
| complete_hiphop_amin_8bar_32 | complete | ok | 0 | verse 16, chorus 8 | - | 0 | 0.0 | 2.1 | 0.0000 | ok |
| complete_jazz_f_8bar_32 | complete | ok | 0 | a_section 8, a_section 8, b_section 8 | - | 0 | 0.0 | 1.6 | 0.0000 | ok |
| complete_pop_c_8bar_32 | complete | ok | 0 | verse 8, chorus 8, verse 4, outro 4 | - | 0 | 0.0 | 2.0 | 0.0000 | ok |
| complete_rock_e_8bar_32 | complete | ok | 0 | verse 8, chorus 8, verse 8 | - | 0 | 0.0 | 2.2 | 0.0000 | ok |
| new_blues_32 | new | ok | 0 | intro 4, verse 12, verse 12, verse 4 | - | 0 | 0.0 | 2.6 | 0.0000 | ok |
| new_blues_64 | new | ok | 0 | intro 4, verse 12, verse 12, verse 12, verse 12, verse 8, outro 4 | - | 0 | 0.0 | 7.6 | 0.0000 | ok |
| new_electronic_32 | new | ok | 0 | intro 8, breakdown 8, drop 16 | - | 0 | 0.0 | 2.6 | 0.0000 | ok |
| new_electronic_64 | new | ok | 0 | intro 8, breakdown 8, drop 16, breakdown 8, drop 16, breakdown 4, outro 4 | - | 0 | 0.0 | 7.7 | 0.0000 | ok |
| new_gospel_32 | new | ok | 0 | intro 4, verse 8, chorus 8, verse 8, chorus 4 | - | 0 | 0.0 | 2.6 | 0.0000 | ok |
| new_gospel_64 | new | ok | 0 | intro 4, verse 8, chorus 8, verse 8, chorus 8, vamp 8, tag 4, verse 8, chorus 4, outro 4 | - | 0 | 0.0 | 7.8 | 0.0000 | ok |
| new_jazz_32 | new | ok | 0 | a_section 8, a_section 8, b_section 8, a_section 8 | - | 0 | 0.0 | 1.8 | 0.0000 | ok |
| new_jazz_64 | new | ok | 0 | a_section 8, a_section 8, b_section 8, a_section 8, a_section 8, a_section 8, b_section 8, a_section 4, outro 4 | - | 0 | 0.0 | 6.7 | 0.0000 | ok |
| new_pop_32 | new | ok | 0 | intro 4, verse 8, chorus 8, verse 8, chorus 4 | - | 0 | 0.0 | 2.3 | 0.0000 | ok |
| new_pop_64 | new | ok | 0 | intro 4, verse 8, chorus 8, verse 8, chorus 8, bridge 8, chorus 8, verse 8, outro 4 | - | 0 | 0.0 | 7.1 | 0.0000 | ok |
| tight_blues_a_12bar_16_high | tight | ok | 0 | verse 4 | - | 0 | 0.0 | 0.2 | 0.0000 | ok |
| tight_blues_e_12bar_48_outro | tight | ok | 0 | verse 12, verse 12, verse 8, outro 4 | - | 0 | 0.0 | 3.1 | 0.0000 | ok |
| tight_folk_g_14bar_16_outro | tight | ok | 0 | outro 2 | - | 0 | 0.0 | 0.3 | 0.0000 | ok |
| tight_pop_c_10bar_32_high | tight | ok | 0 | verse 8, chorus 8, verse 6 | - | 0 | 0.0 | 1.8 | 0.0000 | ok |

## Per request: `meta-low.json`

| request | kind | first pass | revisions | plan | judge | regenerated | plan (s) | total (s) | USD | status |
|---|---|---|---:|---|---|---:|---:|---:|---:|---|
| new_pop_32 | new | ok | 0 | verse 8, pre_chorus 4, chorus 8, verse 4, chorus 8 | regenerate, regenerate | 3 | 5.6 | 19.2 | 0.0182 | ok |
| new_jazz_64 | new | ok | 0 | intro 8, a_section 8, a_section 8, b_section 8, a_section 8, solo 16, outro 8 | accept | 0 | 6.1 | 13.9 | 0.0101 | ok |
| complete_hiphop_amin_8bar_32 | complete | ok | 0 | chorus 8, verse 8, chorus 8 | regenerate, accept | 2 | 3.7 | 13.6 | 0.0121 | ok |
| tight_blues_e_12bar_48_outro | tight | ok | 0 | verse 12, verse 12, outro 12 | accept | 0 | 4.6 | 9.4 | 0.0081 | ok |
| tight_folk_g_14bar_16_outro | tight | ok | 0 | outro 2 | accept | 0 | 2.8 | 5.2 | 0.0065 | ok |
| tight_pop_c_10bar_32_high | tight | ok | 0 | pre_chorus 4, chorus 6, post_chorus 4, bridge 4, chorus 4 | regenerate, accept | 1 | 7.5 | 15.4 | 0.0150 | ok |

## Per request: `meta-medium.json`

| request | kind | first pass | revisions | plan | judge | regenerated | plan (s) | total (s) | USD | status |
|---|---|---|---:|---|---|---:|---:|---:|---:|---|
| complete_bossa_f_16bar_64 | complete | ok | 0 | b_section 16, a_section 16, outro 16 | accept | 0 | 8.2 | 15.9 | 0.0090 | ok |
| complete_country_g_16bar_32 | complete | ok | 0 | bridge 4, chorus 8, outro 4 | regenerate, regenerate | 1 | 14.0 | 22.3 | 0.0217 | ok |
| complete_hiphop_amin_8bar_32 | complete | ok | 0 | chorus 8, verse 8, chorus 8 | accept | 0 | 7.7 | 11.8 | 0.0129 | ok |
| complete_jazz_f_8bar_32 | complete | ok | 0 | a_section 8, b_section 8, a_section 8 | accept | 0 | 5.6 | 8.9 | 0.0098 | ok |
| complete_pop_c_8bar_32 | complete | ok | 0 | pre_chorus 4, chorus 8, bridge 8, outro 4 | regenerate, accept | 2 | 13.6 | 22.7 | 0.0200 | ok |
| complete_rock_e_8bar_32 | complete | ok | 0 | pre_chorus 4, chorus 8, solo 4, bridge 4, chorus 4 | regenerate, regenerate | 2 | 10.1 | 20.5 | 0.0223 | ok |
| new_blues_32 | new | ok | 0 | intro 8, verse 12, verse 12 | accept | 0 | 7.5 | 12.8 | 0.0113 | ok |
| new_blues_64 | new | ok | 0 | intro 4, verse 12, verse 12, solo 12, verse 12, outro 12 | accept | 0 | 7.8 | 18.3 | 0.0135 | ok |
| new_electronic_32 | new | ok | 0 | intro 8, breakdown 8, drop 8, chorus 8 | accept | 0 | 10.8 | 16.7 | 0.0149 | ok |
| new_electronic_64 | new | ok | 0 | intro 8, breakdown 16, drop 8, breakdown 16, drop 8, outro 8 | accept | 0 | 10.8 | 20.6 | 0.0141 | ok |
| new_gospel_32 | new | ok | 0 | intro 4, verse 8, chorus 8, vamp 4, chorus 8 | regenerate, regenerate | 3 | 9.9 | 24.5 | 0.0229 | ok |
| new_gospel_64 | new | ok | 0 | intro 8, verse 8, chorus 8, verse 8, chorus 8, bridge 8, vamp 8, outro 8 | regenerate, regenerate | 3 | 8.7 | 32.0 | 0.0240 | ok |
| new_jazz_32 | new | ok | 0 | a_section 8, a_section 8, b_section 8, a_section 8 | accept | 0 | 4.4 | 12.7 | 0.0110 | ok |
| new_jazz_64 | new | ok | 0 | intro 8, a_section 8, a_section 8, b_section 8, a_section 8, solo 16, outro 8 | accept | 0 | 12.4 | 21.3 | 0.0151 | ok |
| new_pop_32 | new | ok | 0 | intro 4, verse 8, pre_chorus 4, chorus 8, bridge 4, chorus 4 | regenerate, regenerate | 4 | 7.4 | 17.8 | 0.0165 | ok |
| new_pop_64 | new | ok | 0 | intro 4, verse 8, pre_chorus 4, chorus 8, verse 8, pre_chorus 4, chorus 8, bridge 8, chorus 8, outro 4 | regenerate, regenerate | 3 | 5.9 | 24.7 | 0.0185 | ok |
| tight_blues_a_12bar_16_high | tight | ok | 0 | bridge 2, tag 2 | accept | 0 | 9.2 | 14.5 | 0.0161 | ok |
| tight_blues_e_12bar_48_outro | tight | ok | 0 | verse 12, verse 12, outro 12 | accept | 0 | 6.7 | 12.2 | 0.0103 | ok |
| tight_folk_g_14bar_16_outro | tight | ok | 0 | outro 2 | regenerate, regenerate | 1 | 3.9 | 11.4 | 0.0130 | ok |
| tight_pop_c_10bar_32_high | tight | ok | 0 | pre_chorus 4, chorus 8, post_chorus 2, bridge 4, chorus 4 | regenerate, accept | 1 | 10.4 | 20.4 | 0.0212 | ok |

## Per request: `meta-high.json`

| request | kind | first pass | revisions | plan | judge | regenerated | plan (s) | total (s) | USD | status |
|---|---|---|---:|---|---|---:|---:|---:|---:|---|
| new_pop_32 | new | ok | 0 | intro 4, verse 8, pre_chorus 4, chorus 8, verse 4, chorus 4 | regenerate, accept | 1 | 15.5 | 28.3 | 0.0322 | ok |
| new_jazz_64 | new | ok | 0 | intro 4, a_section 8, a_section 8, b_section 8, a_section 8, a_section 8, b_section 8, a_section 8, outro 4 | accept | 0 | 14.5 | 23.5 | 0.0210 | ok |
| complete_hiphop_amin_8bar_32 | complete | ok | 0 | chorus 8, verse 8, chorus 8 | accept | 0 | 7.5 | 14.6 | 0.0151 | ok |
| tight_blues_e_12bar_48_outro | tight | ok | 0 | verse 12, verse 12, outro 12 | accept | 0 | 12.5 | 18.7 | 0.0198 | ok |
| tight_folk_g_14bar_16_outro | tight | ok | 0 | outro 2 | regenerate, regenerate | 1 | 6.3 | 13.1 | 0.0170 | ok |
| tight_pop_c_10bar_32_high | tight | ok | 0 | pre_chorus 4, chorus 8, post_chorus 2, bridge 4, chorus 4 | accept | 0 | 18.1 | 23.0 | 0.0245 | ok |
