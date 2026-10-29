# Fixed-seed paired planner evaluation

3 chord-sampling seeds × 20 public fixtures = 60 paired runs (120 total pipeline executions). Chord checkpoint: `ft_f1` in both arms; Meta model: `muse-spark-1.3`, planning effort `medium`.

## Controls and validation

Each pair has exactly the same normalized request except `planner`, including its derived chord-sampling seed. All seeds cover the same 20 fixtures. The report checks both initial and regenerated section provenance, final section provenance, unique API request attribution, and reconciliation of run, trace, call, API usage, and document costs. The pilot without generation-attempt provenance is excluded; incomplete batches fail validation.

Both arms use temperatures `[0.7, 0.9, 1.1]`, RAG disabled, and voice leading enabled. Request seeds are the base seed plus the first four SHA-256 bytes of the fixture name; section index adds 1009, regeneration adds 1000003, and candidate index adds its zero-based offset (all uint32). The Meta planner is not seeded. The rules arm runs first within each pair. Prompts and JSON schemas are fixed by the product, but their lengths vary with the sketch, plan, and diagnostic report. This compares the full rules pipeline with Meta planning plus judging and possible regeneration; different plans do not imply identical musical material at the same ordinal section seed. Fixing one chord checkpoint deliberately controls that variable; this does not evaluate the quality of genre-specific checkpoint/LoRA selection.

## Per-seed results

| Seed | Completed rules / Meta | Valid plans rules / Meta | Mean distinct types rules / Meta | Meta diatonic lower / equal / higher | Last judge regenerate | Meta API cost |
|---|---|---|---|---|---|---:|
| 1380 | 20/20 / 20/20 | 20/20 / 20/20 | 2.75 / 3.55 | 7 / 2 / 3 | 5/20 | $0.334022 |
| 1381 | 20/20 / 20/20 | 20/20 / 20/20 | 2.75 / 3.50 | 7 / 1 / 4 | 9/20 | $0.352199 |
| 1382 | 20/20 / 20/20 | 20/20 / 20/20 | 2.75 / 3.40 | 5 / 1 / 6 | 7/20 | $0.334327 |

## Hard contracts

| Metric | Rules planner | Muse Spark planner (medium) |
|---|---:|---:|
| Completed traces (`status=ok`) | 60/60 (100.0%) | 60/60 (100.0%) |
| Plans passing the current validator | 60/60 (100.0%) | 60/60 (100.0%) |
| Requested total bar count | 60/60 (100.0%) | 60/60 (100.0%) |
| All generation attempts using `ft_f1` | 282/282 (100.0%) | 331/331 (100.0%) |
| Final sections using `ft_f1` | 282/282 (100.0%) | 274/274 (100.0%) |

The validator checks form constraints such as total length, section/cadence vocabulary, outro placement, and sketch citations. Passing these contracts does not establish good chord choices or perceived musical quality.

## Musical diagnostics (proxies, not quality scores)

| Metric | Rules planner | Muse Spark planner (medium) |
|---|---:|---:|
| Mean distinct section types | 2.75 | 3.48 |
| Rule-forced chord slots | 948/4224 (22.4%) | 836/4224 (19.8%) |
| Out-of-key model slots in diatonic genres | 328/1695 (19.4%) | 259/1759 (14.7%) |
| Empty model slots | 0 | 0 |
| Identical same-type/length section pairs | 0/132 (0.0%) | 0/70 (0.0%) |
| Mean symbol agreement in those pairs | 11.2% | 12.2% |

Paired diatonic diagnostic W/E/L (lower out-of-key share / equal / higher): **19 / 4 / 13**, over 36 request-seed pairs. These are diagnostic wins, not musical-preference wins. Rule-forced slots are excluded from the out-of-key calculation. Its denominator includes all remaining model slots; empty slots are reported separately. Repeated-section agreement uses exact chord symbols in same-type/length pairs; higher repetition can represent consistency or monotony. More section types and fewer out-of-key chords are not universally better.

The diatonic subset uses the product's genres: pop, country, folk, gospel, classical, rock, electronic, hip_hop. For suggestion A, the analyzer removes slash bass and checks whether every parsed chord tone belongs to the key collection. Major uses its major-scale pitch classes; minor uses the union of natural, harmonic, and melodic minor pitch classes. A nonempty symbol the chord parser cannot interpret also counts as outside the collection. This is a strict pitch-collection diagnostic, not a test of functional harmony; borrowed chords and secondary dominants can be musically valid.

Ratios pool their numerators and denominators. Distinct types are averaged across runs; repeated-pair agreement is weighted by the number of comparable section pairs. Each fixture repeats across seeds, so these observations are repeated measurements of 20 fixtures rather than independent musical tasks, and no significance claim is made.

## Judge decisions and execution cost

| Metric | Rules planner | Muse Spark planner (medium) |
|---|---:|---:|
| Runs with regenerated sections | 0/60 (0.0%) | 32/60 (53.3%) |
| Final judge accepted | n/a (no judge) | 39/60 (65.0%) |
| Last judge still requested regeneration | n/a (no judge) | 21/60 (35.0%) |
| Pooled median total latency | 2.040 s | 17.541 s |
| Recorded API calls (ledger entries) | 0 | 152 |
| Recorded prompt / completion tokens | 0 / 0 | 129372 / 220052 |
| Recorded mean Meta API cost per run | $0.000000 | $0.017009 |
| Recorded total Meta API cost | $0.000000 | $1.020549 |

`status=ok` means the bounded pipeline completed, not that the final judge accepted the song. The judge can still request regeneration after its allowed turns or after a section has already been regenerated. Its decisions come from diagnostic reports, not listening, and are not independent human quality judgments. Latency includes execution order, local model loading/cache effects, and network variability.

Last judge still requested regeneration:

- Seed 1380: `complete_hiphop_amin_8bar_32`
- Seed 1380: `new_electronic_64`
- Seed 1380: `new_pop_32`
- Seed 1380: `new_pop_64`
- Seed 1380: `tight_folk_g_14bar_16_outro`
- Seed 1381: `complete_pop_c_8bar_32`
- Seed 1381: `complete_rock_e_8bar_32`
- Seed 1381: `new_electronic_32`
- Seed 1381: `new_gospel_64`
- Seed 1381: `new_pop_32`
- Seed 1381: `new_pop_64`
- Seed 1381: `tight_blues_a_12bar_16_high`
- Seed 1381: `tight_folk_g_14bar_16_outro`
- Seed 1381: `tight_pop_c_10bar_32_high`
- Seed 1382: `complete_hiphop_amin_8bar_32`
- Seed 1382: `complete_rock_e_8bar_32`
- Seed 1382: `new_electronic_64`
- Seed 1382: `new_gospel_32`
- Seed 1382: `new_pop_32`
- Seed 1382: `new_pop_64`
- Seed 1382: `tight_folk_g_14bar_16_outro`

The saved runs included here incurred **$1.020549** in recorded Meta API cost. This excludes pilot and any other batches not supplied to this report. This offline report made **0 additional API calls**, cost **$0 additionally**, and generated no music. No listening test was performed; these results do not prove musical superiority.

Sources: each supplied seed directory's `rules.json` and `meta-medium.json`, plus the public request fixtures. All validation and metrics are reproducible with `agent/report_fixed_seed_plans.py`.
