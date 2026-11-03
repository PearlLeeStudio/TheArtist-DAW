# Two bounded agents

TheArtist has two features where Muse Spark decides the next step itself, through
tool calls or a plan that code validates, and stops when it has a result or hits
a limit. This page describes each loop, its limits, what the musician sees, and
what was measured. By default both run on Standard `muse-spark-1.3` through the
Meta Model API; the judge inside the second loop, and the Reharmonize agent through
its own `agent` client role, can run on Meta open weights
([open weights](open-weights.md)).

## Reharmonize: a tool-call search over substitutions

The musician selects one to four written chords and asks for three alternatives.
Muse Spark then runs the search ([reharmonize_agent.py](../backend/app/services/reharmonize_agent.py)):

1. It chooses which substitution families to search (`common_tones`,
   `modal` or `dominant`: shared-tone substitutes, modal borrowings, and dominant
   approaches including tritone substitutes) and calls
   `search_substitutions`. The tool enumerates the mathematically valid patches
   inside the selected bars and scores every patch with the Music Transformer
   against the surrounding harmony ([reharmonize.py](../backend/app/services/reharmonize.py)).
2. It reads the scored shortlist and may search again with other families.
3. It ends the run with `offer_candidates`: three patches that differ from each
   other, chosen from the pool the tool returned.

| Limit | Value |
|---|---|
| Model turns | at most 4 |
| Tool calls | at most 6; `offer_candidates` must come alone and after at least two searches |
| Wall clock | 100 s for the run, at most 30 s per turn |
| Cost | $0.15 per search by default (worst-case reservation before each turn) |
| Result check | exactly three distinct ids, all from the returned pool, or the run is reported as a failure |
| Scope | nothing outside the selected bars can change |

**What the musician sees.** **Origin / Alter 1–3** cards under the passage, a
yellow box `✓ Meta muse-spark-1.3 chose these alternatives` with the tool calls
and cost, and **Run details** listing each call with its request id, cost and
time. The alternatives can be auditioned and combined on the staff before
**Apply**; Ctrl/⌘+Z undoes. When Meta is off, unconfigured, paused at the credit
stop line or at its limit, the local selector picks three alternatives and the
box says **Picked without Meta** with the reason
([without Meta](reharmonization.md#without-meta)).

**Measured.** Hosted median 10.4 s per search and $0.014–0.021 per search in
recorded runs ([runtime performance](../experiments/speed/runtime-performance.md)).
One recorded run on *Amazing Grace* bars 5–8 with the gospel adapter: two
searches and one offer, three requests, $0.0197, 12.5 s, alternatives D7 → D7b9,
D7 → Ab7#11 and G → G7 ([record](../experiments/meta/reharmonize_amazing_grace.json)).
On 40 JAZZVAR passages with a shared candidate pool and a blinded automatic
judge, Meta's selection scored 2.671 against 2.464 for the own-model-only
selector on a 0–4 scale (paired bootstrap 95% CI for the difference
[+0.042, +0.379]); the judge is the same model family, so this is not a
listening result ([comparison](model-comparison.md#reharmonize-same-passages-three-selection-methods)).

## Complete the form: plan → validate → revise → compose or judge

From an empty score or a sketch, the musician chooses a genre, a length and a
mode. Muse Spark then builds the song form ([planner.py](../backend/app/services/planner.py)):

1. **Plan.** Muse Spark returns the section plan as strict JSON: section types,
   bars per section, a reason per section and citations of the sketch's bars.
2. **Validate.** Code checks the plan: total bars equal the requested length,
   2–32 bars per section, the section and cadence vocabulary, outro placement,
   sketch citations, reason length. Every failed check becomes a message.
3. **Revise.** The messages go back to Muse Spark, which revises the plan; at
   most two revisions.
4. **Fill.** In **Muse Spark only** mode, Muse Spark writes every chord of the
   plan in one call. In **Music Transformer + Meta review** mode, the own model
   generates each section and the judge role reads the analyzer's facts about
   the result and may send back at most two sections per pass for regeneration,
   for at most two passes.

| Limit | Value |
|---|---|
| LLM calls per run | at most 5: 1 plan, up to 2 revisions, then 1 composition or up to 2 judgments |
| Cost | $0.05 worst case per call, $0.10 per run by default |
| Wall clock | 120 s per run |
| Sections one judgment may send back | at most 2 |
| Provenance | every section records its source (`sketch`, `ai` or `rules`) and the model that wrote it |

**What the musician sees.** The planning and composition stages stream to the
dialog; the finished form is applied to the staff with section labels, every
chord editable, and the existing sketch preserved. Each judgment prints its
provider, model, request id and cost.

**Measured.** On the hosted app, an empty score became 32 bars in six sections
in 23.7 s for $0.020 (Muse Spark only). In the fixed-seed comparison, 20 requests
× 3 seeds = 60 paired runs of Muse Spark plan + F1 against the rules template:
structure and length passed 60/60 on both sides; mean distinct section types
2.75 → 3.48; out-of-key slots in genres that stay in key 19.4% → 14.7%; the judge
still requested regeneration in 21/60 final passes; 152 calls, $1.02 in total
([comparison](../experiments/agent_eval/fixed-seed/comparison.md)). More section
types and fewer out-of-key chords are diagnostics, not quality scores.

## Second ear: one observe-then-act judgment

After Generate, **Second ear** asks the judge role to pick one of A/B/C on facts
the analyzer computed, and each reason is checked against the analyzer's value.
In 60 reviews per model, every reason cited the analyzer's value (115/115 on Muse
Spark, 112/112 on Muse Spark Open) and the two models made the same pick in 52/60
([report](../experiments/review_eval/summary.md)).

## Why the loops are bounded

Every call has a timeout, a turn limit and a worst-case cost reservation; its
request id, tokens and cost go to a persistent ledger and onto the screen. A
credit stop line pauses Meta before the balance runs out. A run that hits a limit
or returns an invalid result is reported as a failure with its reason, never
replaced by a result that looks like success. The same services are exposed over
REST and as MCP tools (`plan_song`, `validate_plan`, `generate_section`,
`build_song`, `import_score`, `export_daw` among the eleven), so another agent
can drive them with the same limits ([MCP](mcp.md)).
