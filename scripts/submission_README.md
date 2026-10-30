# TheArtist · Meta hackathon contribution

The existing TheArtist core supplies the score editor, Music Transformer,
trained weights, music utilities and research code. The event contribution adds
Meta score interpretation, context-aware planning and bounded revision,
Original/A/B/C editing, arrangement export, source attribution and performance
improvements. These are development claims; musical preference requires listening.

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
provenance heuristic cannot establish absence of smaller copied fragments.

## Reproduce

Install Git, Python 3.12, uv and Node/npm (tested with Node 25.9.0). Use absolute
paths for the downloaded submission directory and a **new, separate** app directory:

```sh
python3 /absolute/submission/bootstrap.py --target /absolute/theartist-app --install --prepare-assets
```

The bootstrap acquires the fixed core from `PearlLeeStudio/TheArtist`, applies
the verified patch, installs the locked Python/npm dependencies, builds the
frontend, checks the app import and downloads F1 plus reviewed OMT prose.
Network access is required. Cached dependencies are permitted; weights and
theory texts are not distributed in this package. An existing local core mirror
can be specified with `--core-source /absolute/core-mirror` for an offline
**code reconstruction**; dependency and asset installation may still need network.

Run the built application without a paid API:

```sh
uv run --frozen --directory /absolute/theartist-app/backend python /absolute/theartist-app/deploy/serve.py
```

Open `http://localhost:7860`. Use **TheArtist only** for a supported vector PDF
and **Genre template** for full-form creation. The own F1 model and OMT references
are active; unavailable Meta actions remain explicit. To use Meta, set the
server-side `MODEL_API_KEY`, `THEARTIST_META_ENABLED=1`, and the persistent budget
configuration described in `deploy/README.md`. No provider key goes in a browser.
This starts a local server; it does not purchase hosting or configure a domain.

The development snapshot `1be8009` was reconstructed from the public core in a
new checkout, with fresh environments and shared download caches. All 371 changed
file hashes, frozen installs, build, F1/OMT setup and an in-process HTTP path
passed: original 20-bar PDF import → actual F1 completion to 64 bars → four-track
MIDI (metadata plus Harmony/Bass/Drums). This does not verify a Docker image,
external hosting, actual browser audio or human preference. The reconstructed
`scripts/verify_reconstruction.py` can repeat that path with `--root` and a new
absolute `--out` report path.

## Rights and scope

Code remains MIT. Existing model weights/training data retain CC BY-NC 4.0 and
their upstream terms; this is a noncommercial demo/research workflow. OMT uses
only the reviewed original-edition subset with CC BY-SA attribution. Berklee is
off and blocked in public-host mode. No corpora, weights, keys or private planning
documents are included. The app's README contains full dependency attribution.

Suggested video opening: “The score editor and trained music model predate this
event; my hackathon contribution connects Meta score understanding, bounded
composition revision and editable DAW delivery.” The package is not itself a
published hosted app or a completed human listening evaluation.
