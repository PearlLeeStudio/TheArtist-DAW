# TheArtist · Meta hackathon contribution

**From a score or a chord sketch to editable DAW parts: Meta Muse Spark searches the
harmony, my own chord model scores it, the musician chooses.** Indie track · *Build
for Your World* · built October 27 – November 4, 2026 on top of my pre-existing score
editor and Music Transformer.

[Watch the 3-minute demo](https://youtu.be/wC-dkLfot-c) ·
[Demo on X](https://x.com/pearlmedicilee/status/2117606784819249170) ·
[Live app — artist-daw.pearlleestudio.co](https://artist-daw.pearlleestudio.co) ·
[Development repository — TheArtist-DAW](https://github.com/PearlLeeStudio/TheArtist-DAW) ·
[128 recorded contributions](HACKATHON.md)

[![Watch TheArtist's hackathon demo](https://i.ytimg.com/vi/wC-dkLfot-c/hqdefault.jpg)](https://youtu.be/wC-dkLfot-c)

## Why I built it

The chord helpers I used in DAWs suggest the next chord while the song just keeps
growing: no set length, no verses or choruses, no idea where a phrase has to land.
A chord that does not know the song form cannot be suggested well. TheArtist keeps
the form visible, imported from a score or planned by Muse Spark, and works inside
it: Reharmonize changes only the selected bars and scores every alternative against
the surrounding harmony, and the result leaves as separate, editable Harmony, Bass
and Drums MIDI tracks, so the harmony is never typed twice between the score and
the DAW session. It is built for musicians who already have a song on paper and
want assistance, not a generated song: in Tracklib's 2025 survey of 1,734
producers, 6% used generative tools regularly and 82% opposed full-song
generation ([MusicTech](https://musictech.com/news/industry/music-producers-are-rejecting-ai-study-reveals-over-80-of-producers-are-against-ai-generated-songs)).
Each piece exists elsewhere (Logic's Session Players follow a chord track, Scaler
suggests substitutions, Band-in-a-Box arranges typed chords); what is new is the
chain from the printed score to contextual alternatives the musician chooses, a
completed form and editable parts in the DAW.

Existing before the event and not claimed as event work: the score editor (staff,
voicings, Roman numerals, MIDI input, playback), the 31 sounds and genre rhythms,
and the 25M-parameter Music Transformer with its 11 genre adapters. Everything
below was built during the event; the [contribution record](HACKATHON.md) links
each of the 128 additions to its commits, tests and limits.

<p align="center">
  <img src="screenshot/13-reharmonize-alternatives.png" alt="Reharmonize on an imported lead sheet: Origin and Alter 1–3 under the passage, Alter 3 selected, with the Reharmonize controls on the right" width="100%">
  <br>
  <sub>Reharmonize in the live workspace: Muse Spark explores the substitution search through tool calls, the Music Transformer scores the candidates in context, and Alter 1–3 wait under the passage until the musician applies one.</sub>
</p>

## Built this week: a harmony system on two Meta models

| Role | Model | Served by | What it does |
|---|---|---|---|
| Reader, planner | **Muse Spark 1.3** (`muse-spark-1.3`, Standard Meta Model API) | `api.meta.ai` | reads a whole score PDF or image and is compared bar by bar with the local reader; plans a song form as strict JSON; drives the Reharmonize search through native tool calls when the agent role is left on it (the default) |
| Judge and Reharmonize agent | **Muse Spark Open** (`meta-models/muse-spark-open-1026`, Meta open weights) | **Baseten** | Second ear's pick among A/B/C and the hybrid form review; since 2026-11-04 also the Reharmonize search, with the two tools stated as JSON and one checked call per turn; the hosted app runs both roles this way through the judging window |
| Scorer | my Music Transformer (Phase 0, F1–F5, F1 v2, 11 genre LoRAs) | the app server, CPU | generates chords and scores every candidate against the surrounding bars |

**Two bounded agents** ([page](docs/agents.md)).

- *Reharmonize.* Muse Spark chooses which substitution families to search, calls
  `search_substitutions` as often as it needs (at most 4 turns, 6 tool calls, 100 s),
  reads the Music Transformer's context score for every patch the tool returns, and
  ends the run with `offer_candidates`: three patches that differ from each other.
  The musician auditions **Origin / Alter 1–3** on the staff, combines them and
  applies. Hosted median 10.4 s, about $0.02 per search.
  [Agent](backend/app/services/reharmonize_agent.py) · [guide](docs/reharmonization.md) ·
  [one recorded run](experiments/meta/reharmonize_amazing_grace.json)
- *Complete the form.* Muse Spark plans the song form as strict JSON; code checks
  section lengths, recurrence and key and returns the errors; Muse Spark revises (at
  most twice) and then writes every chord of the plan. Empty score → 32 bars in six
  sections on the hosted app: 23.7 s, $0.02. [Planner](backend/app/services/planner.py)

**Every call is accountable.** One provider-agnostic client
([llm.py](backend/app/services/llm.py)) gives each role its own provider, key,
ledger and cap. Every request carries a timeout, a turn limit and a worst-case cost
reservation; its request id, tokens and cost go to a persistent ledger and onto the
screen (**Run details** for the agent, the result line of every judge call). A credit
stop line pauses Meta before the balance runs out. A failed call is shown as a
failure, never as a result that looks like success. Moving the judge to open weights
is four environment lines and the agent five; the result line then reads
`baseten meta-models/muse-spark-open-1026 · <request id> · $<cost>`, and the first
hosted review did (request `54ca701a…`, $0.0045, 5.4 s, every reason confirmed by
the analyzer). The hosted agent followed on 2026-11-04: its first three searches on
open weights each completed `search_substitutions → search_substitutions →
offer_candidates` with three candidates, at $0.0121, $0.0096 and $0.0048 and 11.5,
9.3 and 7.7 s ([record](experiments/meta/reharmonize_open_weights_live.json)).
What runs on open weights and how to verify it:
[open weights](docs/open-weights.md).

**Hosted, instrumented, reproducible.** Docker → Caddy HTTPS → API domain →
Cloudflare Pages, with automatic deployment on push, health checks and rollback
([deployment](docs/web-projects.md)); all 18 released model choices and the Open
Music Theory references load at start; the same service over REST and an MCP server
with 11 tools ([MCP](docs/mcp.md)); a Safari–Logic Pro bridge
([MIDI input and Mac bridge](docs/midi-input.md)) and a Logic Scripter MIDI FX
script ([plugin](plugin/logic-scripter/README.md)); a GitHub Actions workflow that
rebuilds the app from this package in Docker and runs the PDF → F1 → MIDI workflow
over HTTP ([run 41678059725](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/actions/runs/41678059725)).
The automated suites, 687 backend and 320 frontend tests, verify contracts and
editing behavior, not musical quality. [Architecture](docs/architecture.md) ·
[model catalog](docs/models.md)

**From push to production.** Every change takes one path
([automatic deployment](deploy/autodeploy.md), [Pages](deploy/pages.md),
[walkthrough](docs/web-projects.md#from-docker-to-the-public-domains)). A commit
pushed to the public branch is built by Cloudflare Pages into the editor at
artist-daw.pearlleestudio.co, whose worker forwards only `/api` to the model
server and fails closed. The model server's systemd timer polls the same branch
about once a minute over anonymous HTTPS, with no deploy token, webhook or paid
service. A runtime change builds a Docker image labelled with the revision
(dependency and model layers cached); an offline container imports the app as
its runtime user and checks the theory assets; Compose then replaces the app and
waits up to 240 s for health, Caddy is refreshed, all 18 resident models are
identity-checked, three eight-bar F1 candidates are generated without a paid
call, and the public HTTPS endpoint is checked. A build or import failure keeps
the running app; a startup, generation or HTTPS failure restores the previous
checkout and image. Documentation, test, experiment and frontend-only changes
advance the checkout without restarting the API; a runtime change costs a short
interruption while the models reload (not zero-downtime). Secrets live only in
the server's environment file, never in Git, the image or Pages. The same
discipline covers this package: the repository's GitHub Actions workflow clones
it fresh, reconstructs the app with `bootstrap.py`, builds the documented image,
starts it with the full catalog and runs the PDF → F1 → MIDI workflow over HTTP
([workflow](.github/workflows/verify-submission.yml),
[run 41678059725](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/actions/runs/41678059725)).

**Open to other clients over REST and MCP.** Everything the editor does is also a
REST route (22 endpoints: section and song generation, Complete the form,
Reharmonize, Second ear, Import, MIDI and Scripter export, DAW handoff,
capabilities discovery) and, for the arrangement workflow, one of eleven MCP
tools (`import_score`, `plan_song`, `validate_plan`, `generate_section`,
`build_song`, `render_midi`, `export_daw` among them), with the same limits,
provenance fields and ledger, plus an async Python client
([client](backend/theartist_client/client.py)). The second client is
TheVoyager (travel stories with generated music,
[voyager.pearlleestudio.co](https://voyager.pearlleestudio.co)): its Python
adapter requests an arrangement from this service through
`POST /api/generate/song` (the `build_song` MCP tool on a local backend) and
renders it to audio with its own pipeline. The published Voyager plays those
pre-rendered files rather than calling the service live; browser-triggered
generation stays off until the generated accompaniment is good enough for that
use. That song endpoint and the `/api/generate*` chord routes predate the event
and are listed as existing work; the section, plan, review, reharmonize, import
and export routes, the capabilities contract, the MCP server and the client are
this week's. [API spec](https://github.com/PearlLeeStudio/TheArtist-DAW/blob/main/API_SPEC.md) ·
[MCP](docs/mcp.md) · [Voyager API quick start](docs/voyager-api.md)

## Measured so far

Judgments about music are strongly subjective, so a few experts rating a few
examples would not show that one harmony is better than another. How to measure
that quantitatively is a hard, open problem that cannot be solved within a hackathon
week; a proper listening evaluation is planned and will be reported in a paper.
This package reports only what can be measured now: agreement with reference
chords, constraint checks, cost and time. Every number comes from a recorded run
whose calls, costs and failures are kept.

| What was measured | Material | Result |
|---|---|---|
| Reading chords from notes: local analyzer / Muse Spark / hybrid / Muse Spark Open | 40 real progressions in 13 genres, rendered as notes in six voicing variants: 640 slots | exact chords **77.8% → 89.5%** with Muse Spark (+11.7 points, 40 calls, $0.34); hybrid 83.9% for 6 calls / $0.05; Muse Spark Open 89.4% where it answered, 73.8% over all slots (7 of 40 calls failed) · [report](experiments/harmony_eval/summary.md) |
| Reharmonize selectors under a blinded automatic judge | 40 four-bar passages from 16 JAZZVAR tunes, one shared candidate pool, three checkpoint runs | F4 run: local 2.464 / Meta 2.671 / hybrid 2.624 on 0–4; Meta − local **+0.208**, paired bootstrap 95% CI [+0.042, +0.379]; hybrid above local in all three runs · [results](experiments/reharmonization/results.md) |
| Second ear judge on both Meta models | 20 A/B/C lists × 3 orders = 60 reviews per model | every reason cites an analyzer value: **115/115** (Muse Spark) and **112/112** (Muse Spark Open); same pick in **52/60**; $0.0028 vs $0.0041 and 2.1 s vs 2.8 s per review · [report](experiments/review_eval/summary.md) |
| Full-form planner with fixed seeds: Muse Spark plan + F1 vs rules template | 20 requests × 3 seeds = 60 pairs, 152 calls, $1.02 | structure and length 60/60 on both sides; section variety 2.75 → 3.48; out-of-key slots in diatonic genres 19.4% → 14.7%; the judge still asked for regeneration in 21/60 · [comparison](experiments/agent_eval/fixed-seed/comparison.md) |
| Own-model speed with an attention cache, identical outputs | CPU, 4 threads; F1 / F4 / Rock LoRA at 8, 32 and 64 bars; 30 seed-matched pairs | **1.73–3.89× faster**; F1 64 bars 7.18 → 1.85 s; model loading 0.471 → 0.080 s; hosted Reharmonize median 13.8 → 10.4 s · [report](experiments/speed/runtime-performance.md) |
| Reconstruction and DAW execution | this package → Docker → HTTP workflow → Logic Pro | 18 models loaded; a 20-bar original PDF → F1 completion to 64 bars → MIDI with the source chords preserved; opened in Logic Pro as three editable tracks and bounced to a 139.6 s stereo WAV · [record](experiments/speed/reconstruction.json) |

Not claimed: listener preference or musical superiority (no listening study, and
the Reharmonize judge is the same model family as the Meta selector); Import
accuracy on arbitrary PDFs (the local reader supported 0 of 8 Mutopia editions, and
Meta's Bach reading matched 8/32 bars); time saved for a musician (not measured); a
measured Reharmonize comparison on open weights (the hosted demo has run the agent
on Muse Spark Open since 2026-11-04 and three searches are recorded, but the blinded
selector comparison was run with the agent on Muse Spark 1.3 only).
Conditions, intervals and raw records: [evidence](docs/evidence.md) ·
[three-way comparison](docs/model-comparison.md) ·
[evaluation framing](docs/evaluation.md).

## Review the contribution

New source, documentation, benchmark inputs/results and screenshots are ordinary
files in this repository. Start with the evidence and architecture; no
installation or patch application is needed to read them.

| What to inspect | Files in this submission |
|---|---|
| New features and their development commits | [Contribution record](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/blob/main/HACKATHON.md) |
| Model comparisons, measured accuracy, cost and time | [Model comparison](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/blob/main/docs/model-comparison.md), [evidence and limits](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/blob/main/docs/evidence.md) |
| Muse Spark 89.5% vs local 77.8% on 640 notes-to-chords slots | [Benchmark report and raw results](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/tree/main/experiments/harmony_eval) — a separate benchmark, not an Import workflow accuracy claim |
| Muse Spark Open on Baseten: 52/60 matching candidate choices | [Second-ear comparison and both result sets](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/tree/main/experiments/review_eval) |
| System structure, agent flow and model roles | [Architecture](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/blob/main/docs/architecture.md), [Reharmonize](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/blob/main/docs/reharmonization.md), [model catalog](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/blob/main/docs/models.md) |
| Score → harmony → playback → PDF → DAW | [Workflow](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/blob/main/docs/arrangement-workflow.md), [screenshots](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/blob/main/docs/walkthrough.md) |
| All guides and recorded experiments | [Documentation index](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/blob/main/docs/README.md), [experiments](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/tree/main/experiments) |

The ordinary files and `changes.patch` together represent the cumulative change
from the original public `baseline` to the development commit in `manifest.json`.
The patch contains edits/deletions of existing files and four refactored source
files extracted from pre-event code. It does not duplicate the ordinary files.
`manifest.json` pins both revisions, identifies the delivered files and verifies
the core tree plus every reconstructed changed-file hash. The pre-event checkout
and git history are acquired separately, not copied into this repository. The
only development-commit paths left out are the development repository's two
coding-agent instruction files (its `AGENTS.md` and the one-line file that imports
it): tooling rules, not product work.

Reviewed pre-event derivations include `scoreSurface.ts` (staff rendering),
`drumPatterns.ts` (drum patterns), `genres.ts` (genre settings) and
`manualChordDraft.ts` (chord-input logic). Their extraction/refactoring is part
of the patch; their underlying pre-event functionality is not claimed as a new
asset. `provenance-review.json` records the overlap checks. Empty Python package
markers also match existing empty files. The
architecture, model and Voyager API guides reuse material from the original
README; the CPU serving lockfile shares third-party dependency records with the
earlier locks. These are derived documentation and dependency metadata, not new
pre-event capabilities. The provenance heuristic cannot establish absence of
smaller copied fragments.

## Reproduce

Install Git, Python 3.12 and Docker with a running engine. Use absolute paths for
the downloaded submission directory and a **new, separate** app directory.
First reconstruct the source, then let Docker install and prepare the full app:

```sh
git clone https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon.git /absolute/submission
python3 /absolute/submission/bootstrap.py --target /absolute/theartist-app
docker build -f /absolute/theartist-app/deploy/Dockerfile -t theartist-submission /absolute/theartist-app
docker run --rm --name theartist-submission -p 127.0.0.1:7860:7860 --mount type=volume,source=theartist-submission-ledger,target=/data theartist-submission
```

The bootstrap acquires the fixed core from the `baseline` tag of
`PearlLeeStudio/TheArtist-DAW`, which holds the public TheArtist snapshot
(`PearlLeeStudio/TheArtist` commit `f043e53`) unchanged, and checks its
tree hash. The public TheArtist repository keeps only its latest snapshot, so that
commit is no longer served there. The bootstrap verifies the ordinary contribution
files, applies the patch, copies the contribution files into that separate checkout
and checks all changed-file hashes. Docker installs locked dependencies, builds the
frontend, downloads **all seven base checkpoints and eleven genre LoRA adapters**,
and prepares reviewed OMT prose. Startup validates the complete catalog and OMT.
Network access is required. Cached dependencies are permitted; weights and
theory texts are not distributed in this package. An existing local core mirror
can be specified with `--core-source /absolute/core-mirror` for an offline
**code reconstruction**; dependency and asset installation may still need network.

Open `http://localhost:7860`. Leave **Use Meta model** unchecked for a supported vector PDF
and **Genre template** for full-form creation. The own F1 model and OMT references
and the other released model choices are active; unavailable Meta actions remain
explicit. To use Meta, provide a private runtime environment file with
`MODEL_API_KEY`, `THEARTIST_META_ENABLED=1`, `THEARTIST_PUBLIC_META_READER=1` and
persistent usage configuration, as described in the reconstructed app's
`README.md` and `deploy/README.md`. Pass that file with Docker `--env-file` and
keep the ledger volume. No provider key goes in a browser or image.

To reproduce the hosted open-weight judge and agent, add the following to that same
private runtime environment file. The keys are Baseten keys; the reader and planner
continue to use Standard `muse-spark-1.3` with `MODEL_API_KEY`.

```dotenv
LLM_JUDGE_PROVIDER=baseten
LLM_JUDGE_MODEL=meta-models/muse-spark-open-1026
LLM_JUDGE_API_KEY=YOUR_BASETEN_KEY
LLM_JUDGE_REASONING_EFFORT=low
THEARTIST_JUDGE_LEDGER=/data/judge_ledger.json
LLM_AGENT_PROVIDER=baseten
LLM_AGENT_API_KEY=YOUR_BASETEN_KEY
LLM_AGENT_REASONING_EFFORT=low
THEARTIST_AGENT_BUDGET_USD=10
THEARTIST_AGENT_LEDGER=/data/agent_ledger.json
```

Second ear, hybrid form and Reharmonize results identify the provider, model,
request ID and cost. Omitting `LLM_JUDGE_PROVIDER` or `LLM_AGENT_PROVIDER` uses the
default Meta service for that role.

First choose a **Genre** before using New from Song Form. The source-score path
is Import Score → review/edit harmony → Reharmonize → Play → score PDF → MIDI/DAW.
**Open in Logic Pro** from a hosted app additionally needs the local Mac bridge;
**Download MIDI** works without it. See `docs/midi-input.md` in the reconstructed app.
Uploaded scores and parsed notes are used transiently for analysis, not cached
between requests or retained as source content in the editor's saved projects.
With **Use Meta model** checked, the full file is also sent to Meta; the app's
discard policy does not control provider retention. Use your own, public-domain
or appropriately permitted material. The workflow does not grant rights to
arrange or redistribute a protected work.

For native development, the bootstrap's `--install --prepare-assets` flags need
uv and Node/npm and prepare **F1 only** plus OMT. Before running `deploy/serve.py`,
download the complete catalog without `--smoke`:

```sh
uv run --frozen --directory /absolute/theartist-app/backend python /absolute/theartist-app/model/_download.py
HOST=127.0.0.1 uv run --frozen --directory /absolute/theartist-app/backend python /absolute/theartist-app/deploy/serve.py
```

The complete-catalog launcher refuses an F1-only installation. Docker already
performs the full download. For public hosting, the reconstructed
`docs/web-projects.md` explains Docker → Caddy HTTPS → API domain → Cloudflare
Pages → editor domain. Local startup alone does not configure those services.

### Reconstruction verification

Native setup was exercised from the public pinned core in a new checkout with
fresh Python/npm environments and shared download caches. Manifest hashes, frozen
installs, frontend build and app import passed. OMT setup prepared 29 reviewed
passages and the public F1 checkpoint downloaded successfully.

The reconstruction's `scripts/verify_reconstruction.py` passed its in-process HTTP
workflow: original 20-bar PDF import → actual F1 completion to 64 bars → four-track
MIDI (metadata plus Harmony/Bass/Drums), with OMT ready and no Meta call. The original
20 bars retained their chords. Repeat it with `--root` and a new absolute `--out`
report path using the reconstructed backend environment.

The same workflow also passed over live HTTP in a fresh Docker build from the
public submission checkout: all 18 released models loaded, OMT was ready and the
container was healthy. The [Docker run](https://github.com/PearlLeeStudio/TheArtist-Meta-Hackathon/actions/runs/41653628490)
preserves the build and execution logs. Its exported MIDI opened in Logic Pro as
three editable Harmony/Bass/Drums regions spanning 64 bars at 110 BPM, 4/4.
Playback advanced with active track meters; a complete 24-bit, 48 kHz stereo WAV
bounce lasted 139.636 seconds and contained nonzero audio in both channels.
The [measurement record](experiments/speed/reconstruction.json) identifies the
tested revisions, MIDI hash and audio levels. This establishes DAW execution and
audio rendering, not listening preference or browser-audio equivalence.

To repeat the container check, run the repository's **Verify submission in Docker**
workflow from GitHub Actions. It reconstructs the selected revision, builds the
documented image and uploads the report and MIDI for a separate DAW check.

The build retains its chunk-size/deprecated option warnings. npm audit reported
12 moderate findings in the ESLint development
dependency chain and no high or critical findings; those dependencies were not
upgraded as part of packaging.

## Rights and scope

Code remains MIT. Existing model weights/training data retain CC BY-NC 4.0 and
their upstream terms; this is a noncommercial demo/research workflow. OMT uses
only the reviewed original-edition subset with CC BY-SA attribution. Berklee is
off and blocked in public-host mode. No corpora, weights, keys or private planning
documents are included. The app's README contains full dependency attribution.

The package is not itself a published hosted app or a completed human listening
evaluation. The live workspace and hackathon demo are linked above.
