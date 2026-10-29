# AGENTS.md

Working repository of TheArtist for the Meta Global AI Developer Hackathon
(building period Oct 27 – Nov 4, 2026, ET). One rule set for every coding agent;
`CLAUDE.md` imports this file. Do not add agent-specific rule files.

## Ground rules
- Do the work directly. Do not route tasks through agent skills or slash-command workflows.
- Shell commands use absolute paths only (no `cd`, no computed paths); git as `git -C <absolute repo path> …`.
- Read only inside the project tree you were started in (and its subfolders) plus the session scratch directory.
  Never read the user's home directory, other volumes or other projects, even when a tool would allow it.
  Inside the project tree, read freely without asking.
- Everything up to the git tag `baseline` is pre-existing (the public TheArtist release snapshot).
  Hackathon work is every commit after it. Each landed feature gets a row in `HACKATHON.md`.
- Keep this development repository and its history intact. Before the submission deadline, prepare a
  separate fresh public repository created on or after October 26 containing only event work, without
  copying pre-event code or git history. Declare the original core as a separate, versioned dependency
  with reproducible setup instructions; provide edits to existing files as patches. A newly added file
  may contain moved pre-event code, so review provenance rather than relying on git's added-file status.
  Development need not take place in the clean submission repository throughout the event. The
  three-minute video must open by distinguishing the pre-existing core from the event's new work.
- Commit here only for files in this repo, when a unit of work is done: `type(scope): description`,
  scopes `frontend` · `backend` · `agent` · `mcp` · `voyager` · `infra` · `docs`; one logical change per commit.
- This repo is public. Never commit API keys or `.env` files, personal data, model weights, the theory
  corpora (Berklee / Open Music Theory text) or their vector index, or private planning documents.
  The Meta key is read only from the environment variable `MODEL_API_KEY`.
- Meta Model API: Standard model IDs (`muse-spark-1.3`), never Contributor mode. Every call has a request
  timeout, a max-turn count and a cost cap enforced in code, and logs request IDs and token usage.
  Failures are shown as failures, never hidden behind a fallback that looks like success.
- Runtime AI in the product is the TheArtist Music Transformer plus Meta models only (Muse Spark through the
  Meta Model API; Meta open weights such as Muse Spark Open, Muse Glimmer or Llama through a partner or locally).
  Other vendors' models are development tools only and are never called from product code.
- Licenses stay as released: code MIT; model weights and training data CC BY-NC 4.0 (portfolio, demo and research use).
- Before claiming done (no `cd`): `npm --prefix <repo>/frontend run build` and `run lint`,
  `uv run --directory <repo>/backend python -c "import app.main"`, plus the tests the task names.
  Report the actual output; exit code 0 is not proof.
- Commit trailers: `Co-Authored-By` is fine; never add private session links or tool-internal references.

## Commands
- Frontend (from `frontend/`): `npm install`, `npm run dev` (port 5173), `npm run build`, `npm run lint`
- Backend (from `backend/`): `uv run uvicorn app.main:app --reload` (port 8000)
- Weights (from the repo root): `uv run --with huggingface_hub python model/_download.py --smoke`

## Layout
- `frontend/src/engine/` pure music logic (no React) · `frontend/src/store/` Zustand state · `frontend/src/components/` UI
- `backend/app/routes/` → `backend/app/services/` (router–service), schemas in `backend/app/models/schemas.py`,
  inference in `backend/app/services/inference.py`
