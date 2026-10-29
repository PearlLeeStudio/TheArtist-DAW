# Does Muse Spark improve the completed song?

The saved comparison shows more varied forms and a lower aggregate out-of-key
share in the genres the product treats as diatonic. It does **not** establish that
the finished music sounds better. Both planners satisfy every structural constraint,
and neither guarantees consistent returns of a chorus or A section. No listening
test was performed.

This is an offline reanalysis of the same 20 request names in
[`rules.json`](results/rules.json) and [`meta-medium.json`](results/meta-medium.json):
10 new songs, 6 sketch completions and 4 constrained completions. The request metadata
was checked against the saved fixtures, and both sets of plans were rechecked with
the product's current validator. **Additional API calls: 0; additional API cost: $0.**
The API costs and latency below belong to the saved runs, not this reanalysis.

| Metric | Rules planner | Muse Spark planner (medium) |
|---|---:|---:|
| Recorded completed runs | 20/20 (100.0%) | 20/20 (100.0%) |
| Plans passing the current validator | 20/20 (100.0%) | 20/20 (100.0%) |
| Requested total bar count | 20/20 (100.0%) | 20/20 (100.0%) |
| Mean distinct section types | 2.75 | 3.45 |
| Sections recorded as AI generated | 94/94 (100.0%) | 91/91 (100.0%) |
| Rule-forced chord slots | 316/1408 (22.4%) | 289/1408 (20.5%) |
| Out-of-key model slots in diatonic genres | 187/565 (33.1%) | 146/573 (25.5%) |
| Empty model slots | 0 | 0 |
| Identical sequences among same-type/length section pairs | 0/44 (0.0%) | 0/23 (0.0%) |
| Mean symbol agreement in those pairs | 11.1% | 12.2% |
| Runs with regenerated sections | 0/20 (0.0%) | 9/20 (45.0%) |
| Last judge still requested regeneration | n/a (no judge) | 7/20 (35.0%) |
| Recorded median total latency | 2.408 s | 18.082 s |
| Recorded mean Meta API cost per run | $0.000000 | $0.015906 |
| Recorded total Meta API cost | $0.000000 | $0.318111 |

## What this supports

The rules baseline uses genre templates for the form and the author's neural chord
model for its chords. All 94 baseline sections and all 91 Meta sections are recorded
with `source: "ai"`; this is not a comparison with the chord generator's rule-based
fallback. Muse Spark chooses the form, section lengths and cadences, then judges the
generated sections. It does not replace the author's chord model.

Muse Spark used more distinct section types on average. That demonstrates a change
in form, not inherently better composition: a simple repeated form may suit a song.
The hard validator checks section types and lengths, total bars, intro/outro
placement, the final cadence and cited sketch bars/Roman numerals. It does not judge
whether a transition is expressive or a chorus memorable.

The out-of-key diagnostic uses only the 12 requests whose genres appear in the
product's `DIATONIC_GENRES`. It counts model-decided chord slots after excluding the
recorded `rulesSlots`; a chord is outside the key when its pitch classes do not all
fit the analyzer's key collection. The aggregate share drops from 33.1% to 25.5%,
but by paired request Meta is lower in **6**, equal in **1**, and higher in **5**.
Borrowed chords can be intentional, so this is not a musical quality score.

The 316 and 289 rule-forced slots include the section and cadence rules. An ending
written by a deterministic rule is not evidence that the neural model independently
learned that cadence. Fewer forced slots also do not establish better music.

## What remains unproven

**A completed run is not a final quality approval.** Nine Meta runs regenerated
sections, but seven still ended with a judge decision of `regenerate`. The controller
limits judgment calls and regenerates each section at most once. It can therefore
finish with `status: "ok"` without a final `accept`, including when the final
regeneration has no subsequent judgment. Those seven requests are:

- `complete_country_g_16bar_32`
- `complete_rock_e_8bar_32`
- `new_gospel_32`
- `new_gospel_64`
- `new_pop_32`
- `new_pop_64`
- `tight_folk_g_14bar_16_outro`

**Repeated-section coherence is not enforced.** For each song, the diagnostic pairs
generated sections with the same type and length and compares their first
suggestion's chord symbols at corresponding slots. No pair has an identical whole
sequence in either arm. The planner's existing `repeatRate` compares a section with
the immediately preceding material, not with the earlier occurrence of the same
chorus or A section. Exact repetition is not always desirable, but the system has no
explicit test of whether a recurring theme is recognizably preserved. The different
numbers of comparable pairs also prevent interpreting their agreement rates as a
controlled quality ranking.

**The comparison does not isolate causality.** The requests are paired, but the
saved evaluation did not fix the chord generator's sampling seed. The plans differ
in section lengths and contexts, and Meta also adds a regeneration loop. These are
whole-pipeline observations, not an isolated estimate of the planner's effect on
chord quality. The sample contains 20 self-written prompts and no repeated trials or
blind listener preferences.

## Reproduce without spending

[`agent/compare_saved_plans.py`](../../agent/compare_saved_plans.py) reads result
files and request fixtures and prints the table. It does not generate music, create
a client, call an API or write result files. Supply `--rules` with `rules.json`,
`--meta` with `meta-medium.json`, and `--requests` with this directory's `requests`
folder. It rejects duplicate or unpaired request names and metadata that no longer
matches the fixtures.

For a claim about musical completion, the next comparison needs controlled chord
sampling, explicit checks of recurring sections and transitions, and blind listening
to matched exports. The current evidence supports functional integration and some
measurable changes in structure; it does not support a claim of musical superiority.
