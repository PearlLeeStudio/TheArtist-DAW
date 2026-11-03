# TheArtist · Meta hackathon contribution

[Watch the hackathon demo](https://youtu.be/wC-dkLfot-c) ·
[Try the live workspace](https://artist-daw.pearlleestudio.co) ·
[Development repository](https://github.com/PearlLeeStudio/TheArtist-DAW)

TheArtist helps musicians save preparation time between a score and a DAW
session: extract chords from a supported score or enter a sketch, revise harmony
in context, audition accompaniment, then continue with separate editable Harmony,
Bass and Drums MIDI tracks. Reusing the same harmony reduces repeated chord entry
and setup; the musician shapes the arrangement and finishes it in the DAW.

The existing TheArtist core supplies the score editor, Music Transformer,
trained weights, music utilities and research code. The event contribution adds
Muse Spark score interpretation, form planning and tool-driven reharmonization;
Muse Spark Open on Baseten for Second ear and hybrid form review; Origin/Alter 1–3
editing; the redesigned player and mixer; score PDF and arrangement MIDI export;
the hosted app and Safari–Logic bridge; source attribution and performance work.
These are development claims. Listening evaluation is planned and will be reported
in a paper; the recorded automated measurements do not establish musical preference.

This package contains event changes as a patch, not a copy of the pre-event
checkout or its git history. `manifest.json` pins the original public core and
the development snapshot, verifies the core tree and hashes every changed file.
`provenance-review.json` flags added files that overlap earlier code; being new
to git does not make all of a file's content a new contribution. The complete
feature history and evaluation limitations are in the reconstructed app's
`HACKATHON.md` and `experiments/` directory.

Reviewed pre-event derivations include `scoreSurface.ts` (staff rendering),
`drumPatterns.ts` (drum patterns), `genres.ts` (genre settings) and
`manualChordDraft.ts` (chord-input logic). Their extraction/refactoring is part
of the patch; their underlying pre-event functionality is not claimed as a new
asset. Empty Python package markers also match existing empty files. The
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
python3 /absolute/submission/bootstrap.py --target /absolute/theartist-app
docker build -f /absolute/theartist-app/deploy/Dockerfile -t theartist-submission /absolute/theartist-app
docker run --rm --name theartist-submission -p 127.0.0.1:7860:7860 --mount type=volume,source=theartist-submission-ledger,target=/data theartist-submission
```

The bootstrap acquires the fixed core from the `baseline` tag of
`PearlLeeStudio/TheArtist-DAW`, which holds the public TheArtist snapshot
(`PearlLeeStudio/TheArtist` commit `f043e53`) unchanged, and checks its
tree hash. The public TheArtist repository keeps only its latest snapshot, so that
commit is no longer served there. The bootstrap applies the verified patch and
checks changed-file hashes. Docker installs locked dependencies, builds the
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

To reproduce the hosted open-weight judge, add the following to that same private
runtime environment file. The key is a Baseten key; the reader, planner and
Reharmonize agent continue to use Standard `muse-spark-1.3` with `MODEL_API_KEY`.

```dotenv
LLM_JUDGE_PROVIDER=baseten
LLM_JUDGE_MODEL=meta-models/muse-spark-open-1026
LLM_JUDGE_API_KEY=YOUR_BASETEN_KEY
LLM_JUDGE_REASONING_EFFORT=low
THEARTIST_JUDGE_LEDGER=/data/judge_ledger.json
```

Second ear and hybrid form results identify the provider, model, request ID and
cost. Omitting `LLM_JUDGE_PROVIDER` uses the default Meta service for these jobs.

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

### Recorded reconstruction scope

The development snapshot `53a9c72` was reconstructed from the `baseline` tag in a
new checkout, with fresh environments and shared download caches. All 510 changed
file hashes, frozen installs, the frontend build and the app import passed, and the
reconstruction's `scripts/verify_reconstruction.py` passed its in-process HTTP path:
original 20-bar PDF import → actual F1 completion to 64 bars → four-track MIDI
(metadata plus Harmony/Bass/Drums), with OMT ready and no Meta call. In that run the
build machine's network sandbox cut Python downloads, so the seven OMT pages were
fetched with curl and passed to the reconstruction's own setup code, which still
checked every reviewed paragraph's hash, and the released F1 directory was copied
from an earlier download of the same release. This does not verify a Docker image,
external hosting, actual browser audio or human preference. The reconstructed
`scripts/verify_reconstruction.py` can repeat that path with `--root` and a new
absolute `--out` report path.

## Rights and scope

Code remains MIT. Existing model weights/training data retain CC BY-NC 4.0 and
their upstream terms; this is a noncommercial demo/research workflow. OMT uses
only the reviewed original-edition subset with CC BY-SA attribution. Berklee is
off and blocked in public-host mode. No corpora, weights, keys or private planning
documents are included. The app's README contains full dependency attribution.

The package is not itself a published hosted app or a completed human listening
evaluation. The live workspace and hackathon demo are linked above.
