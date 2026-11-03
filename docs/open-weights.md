# Meta open weights in TheArtist

One page for whoever verifies the open-weight bonus: what runs on Meta open
weights, how to see it on the live app and in the server records, how it was
measured, and what does not run on open weights.

## What runs on open weights

The product's LLM work is split into roles. The **judge role** runs on Meta's
open-weight **Muse Spark Open** (`meta-models/muse-spark-open-1026`), served by
Baseten at `https://inference.baseten.co/v1`. The hosted demo
([artist-daw.pearlleestudio.co](https://artist-daw.pearlleestudio.co)) has run
the judge this way since the evening of 2026-11-03 and keeps it that way through
the judging window.

| Feature | What the judge decides | Code |
|---|---|---|
| **Second ear** (after Generate) | picks one of the A/B/C candidates on facts the analyzer computed (chords outside the key, repetition of the previous section, mean Sethares roughness, changed slots, rules-written slots); each reason is checked against the analyzer's value and marked *analyzer confirmed* or *model statement* | [review.py](../backend/app/services/review.py) |
| **Complete the form → Music Transformer + Meta review** | one observe-then-act judgment per pass over the generated sections, at most two passes, sending back at most two sections for regeneration | [planner.py](../backend/app/services/planner.py) |

The other roles stay on Standard **Muse Spark 1.3** through the Meta Model API:
reading a score PDF or image, planning and writing the song form, and the
Reharmonize tool-call search. [Which model does what](../README.md#hackathon-work-and-where-meta-is-used).

## How to verify it

**On the screen.** Every judge result prints its provider, model, request id and
cost. With the judge on open weights, the result line of a Second ear review and
of each judgment in Complete the form reads

```text
baseten meta-models/muse-spark-open-1026 · <request id> · $<cost>
```

On the live app: choose a **Genre**, drag across a few bars, **Generate**, then
**Second ear**. The result line names the provider and model. A failed call is
shown as a failure with the provider's status; it is never turned into a result
that looks like success.

**In the API.** The same fields are in the responses: `provider`, `model`,
`requestId` and `costUsd` on a review result and on every call of a plan trace
(`calls.*.provider`, `calls.*.model`, `calls.*.requestId`).

**On the server.** The judge role has its own ledger (`THEARTIST_JUDGE_LEDGER`)
with one line per request: request id (Baseten's `x-baseten-request-id` header),
prompt and completion tokens, settled cost and latency. Its cap is
`THEARTIST_JUDGE_BUDGET_USD` (default $10), separate from the Muse Spark ledger.

**How it is switched.** Four lines in the server environment move the judge role
to open weights; nothing else changes and no code is rebuilt
([runtime settings](../deploy/env.example)):

```bash
LLM_JUDGE_PROVIDER=baseten            # base URL and model default to Baseten's
LLM_JUDGE_API_KEY=...                 # Baseten API key, server side only
LLM_JUDGE_REASONING_EFFORT=low        # the setting the comparison used
THEARTIST_JUDGE_BUDGET_USD=10         # the judge's own cap
```

Leaving `LLM_JUDGE_PROVIDER` empty makes the judge the default Muse Spark client.
The client is the same OpenAI-compatible transport for both providers
([llm.py](../backend/app/services/llm.py)); Baseten's list price for Muse Spark Open
is built in, so the worst-case cost reservation and the ledger work the same way.
Because an open-weight endpoint does not enforce the JSON schema server-side, a
reply that fails the schema gets one guarded retry, and the reservation for a
judge call on open weights is doubled to cover it ([review.py](../backend/app/services/review.py)).

**First hosted review on open weights** (2026-11-03): request
`54ca701a1a106f7d176838a17f443fb7df547`, $0.0045, 5.4 s, both reasons confirmed by
the analyzer ([record](../HACKATHON.md), row 127).

## How it was measured

Both measurements ran the product's own code paths against the same inputs on
both Meta models, with every request id, cost, latency and failure kept.

**Second ear, 60 reviews per model** ([report](../experiments/review_eval/summary.md),
[open-weight results](../experiments/review_eval/results-openweight.json),
[Muse Spark results](../experiments/review_eval/results-meta.json)): 20 A/B/C lists
from a planner run, each shown in its three cyclic orders.

| | Muse Spark 1.3 | Muse Spark Open on Baseten |
|---|---:|---:|
| Completed reviews, valid JSON, no retry | 60/60 | 60/60 |
| Reasons that cite an analyzer value at the analyzer's value | 115/115 | 112/112 |
| Most in-key candidate picked in genres that stay in key | 33/36 | 33/36 |
| Same candidate in all three orders | 17/20 | 16/20 |
| Same pick as Muse Spark | — | **52/60** |
| Cost per review · p50 latency | $0.0041 · 2.8 s | **$0.0028 · 2.1 s** |

**Reading chords from notes, 640 slots** ([report](../experiments/harmony_eval/summary.md),
[open-weight results](../experiments/harmony_eval/results-real-songs-openweight.json)):
40 real progressions in 13 genres rendered as notes in six voicing variants, the
same task the product's note interpretation uses.

| | Local analyzer | Muse Spark 1.3 | Muse Spark Open (effort high) |
|---|---:|---:|---:|
| Exact where answered | 95.4% | 89.5% | **89.4%** |
| Coverage | 81.6% | 100% | 82.5% |
| Exact over all 640 slots | 77.8% | **89.5%** | 73.8% |
| Calls · failed | 0 | 40 · 0 | 40 · 7 (4 length limit, 3 harmony validation) |
| p50 per call · total cost | — | 5.1 s · $0.34 | 8.0 s · $0.63 |

Where Muse Spark Open answered, it was as exact as Muse Spark; the lost calls put
its overall agreement below the local analyzer. That is why the product ships
reading, planning and the agent on Muse Spark 1.3 and the judge on open weights:
the judge is the role where the open weights matched the hosted model's choices
at lower cost and latency.

## What does not run on open weights

- **The Reharmonize agent, on the hosted demo.** The agent is its own client role
  (`LLM_AGENT_*`): off Meta Standard the two tools are stated in the system message
  and each turn is one checked strict-JSON call, so it can run on Muse Spark Open.
  No comparison was recorded there, and the hosted demo keeps the agent on Muse
  Spark 1.3 unless the operator switches it; Run details name the model either way.
- **Score reading.** The whole-file PDF/image reading uses the Meta Model API.
- **Listening quality.** No listening study was run; "same pick" and
  "reasons confirmed" are agreement and consistency measures, not preference.

If Baseten is unavailable during judging, Second ear and the hybrid form review
show that failure with the provider's status; Generate, Import, Reharmonize and
Muse Spark only continue on Muse Spark 1.3.
