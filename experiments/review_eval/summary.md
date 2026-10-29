# Second-ear evaluation: does the judge pick among A/B/C better than the R1 order?

20 A/B/C lists (the first section of each planner-evaluation run, real chord-model
candidates), each judged in the three cyclic orders of its candidates, by the product's
`review_candidates` on 2026-10-29: 60 reviews with **Muse Spark 1.3** (the judge role as
shipped) and 60 with **Muse Spark Open on Baseten** (the judge role with
`LLM_JUDGE_PROVIDER=baseten`, its own ledger), effort low, the product's own limits.
Code computes every fact (chords outside the key, repetition of the previous section,
mean Sethares roughness, changed slots, rules-written slots); a reason is *confirmed*
only when the value it cites is the analyzer's value for the candidate it chose.

## What the numbers show

- **The reasons are true.** Every reason both judges gave cited a fact at the value
  the analyzer computed: 115 of 115 (Muse Spark) and 112 of 112 (Muse Spark Open), over
  60 completed reviews each. No invented numbers.
- **It is not the R1 order again.** Muse Spark picked the lowest-roughness candidate in
  35 of 60 reviews (58%; a random pick would in 33%), Muse Spark Open in 30 of 60 (50%).
  Where they differ, they trade roughness for the genre: in the 12 lists of genres that
  usually stay in key, both picked the most in-key candidate in 33 of 36 reviews (92%),
  against 67% for the R1 pick and 72% for a random pick; in jazz, bossa and blues they
  accept chromatic candidates, as the review prompt asks.
- **Little position bias.** Each list was shown in three orders so that every candidate
  sat under every letter once. Muse Spark chose the same candidate in all three orders
  for 17 of 20 lists (85%; 54 of 60 order pairs), Muse Spark Open for 16 of 20 (80%); over
  all orders the shown letters were picked 21 / 22 / 17 and 19 / 22 / 19 times, where a
  judge that went by the letter would pile onto one.
- **The open-weight judge can carry the role.** Muse Spark Open completed 60 of 60 with
  valid JSON on every reply and no retry, chose the same candidate as Muse Spark in 52 of
  60 reviews (87%), and cost $0.0028 per review against $0.0041 (p50 2.1 s against
  2.8 s). Totals: $0.244 (Meta ledger) and $0.168 (judge ledger) for 60 reviews each.

## What they do not show

- **That the picks sound better.** No listening test was run. "Better than R1" here
  means the choices follow the stated genre rule and the reasons are true, not that a
  musician prefers them.
- **Generality.** N = 20 lists from one planner run (10 genres), one day, one prompt.
  The facts are coarse; `changedSlots` is the same for every candidate of a placed
  section (its original bars are empty), so neither judge cited it.
- **Claim direction.** *Confirmed* checks the cited value, not the sentence around it.
  Of the confirmed reasons, the chosen candidate held the strict lowest value of the
  cited fact in 42 (Muse Spark) and 39 (Muse Spark Open), the strict highest in 13 and
  16, and neither (a tie, mostly an out-of-key share of 0 that several candidates share,
  or the middle) in the rest.
- **The R1 baseline is two things.** The editor's A/B/C order is the R1 rerank over the
  model's chords before voice leading and the song-form rules; the review's roughness
  fact is over the chords as they land on the score. Stored A held the lowest roughness
  of the review's table in only 8 of 20 lists (15 of 20 over the chords without slash
  basses and rules slots), so both baselines are reported. In 4 lists the planner's
  cadence wrote slots that a review request (which carries no cadence) cannot mark.

## Method

- Inputs: `experiments/agent_eval/results/meta-medium.json`, first section of each of
  the 20 runs, three stored candidates each, turned into the request the editor sends
  for a placed section (`reviewStore.buildReviewRequest`: chords as the editor writes
  them, empty original bars, the section type, the sketch section before it).
- Orders: ABC, BCA, CAB (the stored letters shown as A, B, C).
- Failures count: a failed review is no agreement in the (all) columns; cost and latency
  include it. None failed in these runs.
- Runner: `backend/scripts/review_eval.py` (21 tests with fake transports). Its first
  version was reviewed independently before any paid call; the 13 confirmed findings
  (the reversed second order left B in place, refused reviews broke the retry count,
  failures were left out of agreement, baselines covered other lists, among others)
  were fixed first.
- Results: `results-meta.json`, `results-openweight.json` (every review with its
  request id, cost, latency, reasons and the facts). The tables below are the output of
  `bash scripts/dev.sh py -m scripts.review_eval --report`.

## Inputs

20 A/B/C lists, the first section of each run in `experiments/agent_eval/results/meta-medium.json` (meta planner, effort medium, run 2026-10-29T09:19:51+00:00, sha256 `f7e68cbdbc22…`): 10 new songs, 6 completions and 4 tight completions in 10 genres (12 lists in genres that usually stay in key); section lengths (lists × bars) 2 × 2, 8 × 4, 8 × 8, 1 × 12, 1 × 16; 10 with a previous section. Each list is judged in the 3 cyclic orders ABC, BCA, CAB (the stored letters shown as A, B, C). R1 ties: 0, lists without R1: 0. Stored A holds the lowest r1Roughness of the review's fact table in 8 of 20 lists, and the lowest R1 over the same chords without slash basses and rules slots (closer to what the rerank scored) in 15; a random pick would agree with the R1 pick 33% of the time.

In 4 lists (new_blues_32, new_blues_64, new_gospel_32, tight_pop_c_10bar_32_high, marked † below) the planner's cadence wrote slots the review's rulesSlots do not list (a review request carries no cadence, so its rules slots are the section type's default): the judge saw those rules-written chords as the model's.

## Each judge and order

| | reviews | completed | shown A / B / C | agrees with R1 pick (all) | agrees with R1 pick (completed) | agrees with stored A (all) | agrees with stored A (completed) | reasons / review | reasons confirmed | confirmed fact: lowest / highest / neither | USD / review | USD total | p50 / p95 (s) | requests sent | JSON validity | failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| meta, order ABC | 20 | 20/20 (100%) | 8 / 7 / 5 | 12/20 (60%) | 12/20 (60%) | 8/20 (40%) | 8/20 (40%) | 1.90 | 38/38 (100%) | 14 / 4 / 20 | 0.0043 | 0.0853 | 3.1 / 5.7 | 20 (0 retries) | 100% | none |
| meta, order BCA | 20 | 20/20 (100%) | 7 / 7 / 6 | 11/20 (55%) | 11/20 (55%) | 6/20 (30%) | 6/20 (30%) | 1.90 | 38/38 (100%) | 13 / 5 / 20 | 0.0039 | 0.0787 | 2.7 / 4.1 | 20 (0 retries) | 100% | none |
| meta, order CAB | 20 | 20/20 (100%) | 6 / 8 / 6 | 12/20 (60%) | 12/20 (60%) | 8/20 (40%) | 8/20 (40%) | 1.95 | 39/39 (100%) | 15 / 4 / 20 | 0.0040 | 0.0803 | 2.8 / 6.3 | 20 (0 retries) | 100% | none |
| meta, all orders | 60 | 60/60 (100%) | 21 / 22 / 17 | 35/60 (58%) | 35/60 (58%) | 22/60 (37%) | 22/60 (37%) | 1.92 | 115/115 (100%) | 42 / 13 / 60 | 0.0041 | 0.2444 | 2.8 / 5.8 | 60 (0 retries) | 100% | none |
| openweight, order ABC | 20 | 20/20 (100%) | 7 / 7 / 6 | 9/20 (45%) | 9/20 (45%) | 7/20 (35%) | 7/20 (35%) | 1.85 | 37/37 (100%) | 12 / 6 / 19 | 0.0028 | 0.0558 | 1.8 / 4.2 | 20 (0 retries) | 100% | none |
| openweight, order BCA | 20 | 20/20 (100%) | 7 / 7 / 6 | 10/20 (50%) | 10/20 (50%) | 6/20 (30%) | 6/20 (30%) | 1.95 | 39/39 (100%) | 11 / 7 / 21 | 0.0027 | 0.0546 | 2.2 / 4.3 | 20 (0 retries) | 100% | none |
| openweight, order CAB | 20 | 20/20 (100%) | 5 / 8 / 7 | 11/20 (55%) | 11/20 (55%) | 8/20 (40%) | 8/20 (40%) | 1.80 | 36/36 (100%) | 16 / 3 / 17 | 0.0029 | 0.0573 | 2.1 / 5.2 | 20 (0 retries) | 100% | none |
| openweight, all orders | 60 | 60/60 (100%) | 19 / 22 / 19 | 30/60 (50%) | 30/60 (50%) | 21/60 (35%) | 21/60 (35%) | 1.87 | 112/112 (100%) | 39 / 16 / 57 | 0.0028 | 0.1678 | 2.1 / 4.5 | 60 (0 retries) | 100% | none |

A failed review counts as no agreement in the (all) columns and is left out of the (completed) ones; cost and latency cover every review that sent a request, failures included. JSON validity is the share of replies that held the schema's JSON; a timeout, connection or HTTP error got no reply and is left out, a reply cut at the token limit or empty counts as not JSON. Over all orders a judge that chooses by the chords picks each shown letter equally often.

- `meta`: meta (meta muse-spark-1.3, effort low), 2026-10-29T13:58:08+00:00, 60 reviews; ledger `backend/.ledger/meta_ledger.json` $4.8997 → $5.1441 of $25.00; limits {'maxUsd': 1.5, 'reviewMaxUsd': 0.03, 'reviewMaxTokens': 2048, 'reviewTimeoutS': 30.0}
- `openweight`: openweight (baseten meta-models/muse-spark-open-1026, effort low), 2026-10-29T13:58:08+00:00, 60 reviews; ledger `backend/.ledger/judge_ledger.json` $0.0000 → $0.1678 of $10.00; limits {'maxUsd': 1.5, 'reviewMaxUsd': 0.03, 'reviewMaxTokens': 2048, 'reviewTimeoutS': 30.0}

## Position consistency and what the picks look like (all orders pooled)

| | sections every order completed | sections with a failed order | same candidate in all orders | same candidate, order pairs | picks: stored A / B / C | picks: conservative / balanced / creative | mean r1Roughness | mean outOfKeyRatio | diatonic genres: most in-key |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| meta | 20 | 0 | 17/20 (85%) | 54/60 (90%) | 22 / 20 / 18 | 21 / 8 / 31 | 0.606 | 0.137 | 33/36 (92%) |
| openweight | 20 | 0 | 16/20 (80%) | 52/60 (87%) | 21 / 21 / 18 | 18 / 10 / 32 | 0.626 | 0.148 | 33/36 (92%) |

The two judges chose the same candidate in 52/60 (87%) of the reviews both completed (same section, same order).

The baselines over the same completed reviews (one row per judge):

| judge | baseline | N | mean r1Roughness | mean outOfKeyRatio | diatonic genres: most in-key |
|---|---|---:|---:|---:|---:|
| meta | R1 pick (lowest r1Roughness) | 60 | 0.567 | 0.102 | 24/36 (67%) |
| meta | stored A (the planner run's order) | 60 | 0.610 | 0.134 | 27/36 (75%) |
| meta | random pick (expected) | 60 | 0.645 | 0.152 | 72% |
| openweight | R1 pick (lowest r1Roughness) | 60 | 0.567 | 0.102 | 24/36 (67%) |
| openweight | stored A (the planner run's order) | 60 | 0.610 | 0.134 | 27/36 (75%) |
| openweight | random pick (expected) | 60 | 0.645 | 0.152 | 72% |

## Facts the reasons cite

| judge | fact | cited | confirmed |
|---|---|---:|---:|
| meta | outOfKeyRatio | 55 | 55/55 (100%) |
| meta | changedSlots | 0 | - |
| meta | repetitionVsPrevious | 24 | 24/24 (100%) |
| meta | r1Roughness | 36 | 36/36 (100%) |
| openweight | outOfKeyRatio | 51 | 51/51 (100%) |
| openweight | changedSlots | 0 | - |
| openweight | repetitionVsPrevious | 22 | 22/22 (100%) |
| openweight | r1Roughness | 39 | 39/39 (100%) |

## Per section (stored letters)

| request | genre | section | bars | R1 pick | meta ABC | meta BCA | meta CAB | openweight ABC | openweight BCA | openweight CAB |
|---|---|---|---:|---|---|---|---|---|---|---|
| complete_bossa_f_16bar_64 | bossa | b_section | 16 | C | C (2/2) | C (2/2) | C (2/2) | A (2/2) | C (2/2) | A (2/2) |
| complete_country_g_16bar_32 | country | bridge | 4 | C | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) |
| complete_hiphop_amin_8bar_32 | hip_hop | chorus | 8 | A | C (2/2) | C (2/2) | C (2/2) | C (2/2) | C (2/2) | C (2/2) |
| complete_jazz_f_8bar_32 | jazz | a_section | 8 | B | A (2/2) | C (2/2) | A (2/2) | A (2/2) | A (2/2) | A (2/2) |
| complete_pop_c_8bar_32 | pop | pre_chorus | 4 | B | A (2/2) | A (2/2) | A (2/2) | A (2/2) | A (2/2) | A (2/2) |
| complete_rock_e_8bar_32 | rock | pre_chorus | 4 | C | A (2/2) | A (2/2) | A (2/2) | A (2/2) | A (2/2) | A (2/2) |
| new_blues_32 | blues | intro† | 8 | B | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) |
| new_blues_64 | blues | intro† | 4 | B | C (1/1) | C (1/1) | C (1/1) | C (2/2) | C (2/2) | B (1/1) |
| new_electronic_32 | electronic | intro | 8 | A | A (2/2) | A (2/2) | A (2/2) | A (2/2) | A (2/2) | A (1/1) |
| new_electronic_64 | electronic | intro | 8 | A | A (2/2) | A (2/2) | A (2/2) | A (1/1) | A (2/2) | A (1/1) |
| new_gospel_32 | gospel | intro† | 4 | B | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) |
| new_gospel_64 | gospel | intro | 8 | A | A (2/2) | A (2/2) | A (2/2) | A (2/2) | A (2/2) | A (2/2) |
| new_jazz_32 | jazz | a_section | 8 | A | B (1/1) | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) |
| new_jazz_64 | jazz | intro | 8 | A | A (2/2) | C (1/1) | A (2/2) | C (1/1) | C (1/1) | C (1/1) |
| new_pop_32 | pop | intro | 4 | B | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) |
| new_pop_64 | pop | intro | 4 | C | C (2/2) | C (2/2) | C (2/2) | C (1/1) | C (2/2) | C (2/2) |
| tight_blues_a_12bar_16_high | blues | bridge | 2 | A | B (2/2) | B (2/2) | C (2/2) | B (2/2) | B (2/2) | C (2/2) |
| tight_blues_e_12bar_48_outro | blues | verse | 12 | A | A (2/2) | A (2/2) | A (2/2) | C (2/2) | C (2/2) | A (2/2) |
| tight_folk_g_14bar_16_outro | folk | outro | 2 | C | C (2/2) | C (2/2) | C (2/2) | C (2/2) | C (2/2) | C (2/2) |
| tight_pop_c_10bar_32_high | pop | pre_chorus† | 4 | B | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) | B (2/2) |

A cell is the stored letter the judge chose and its confirmed / stated reasons.
