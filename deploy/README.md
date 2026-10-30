# Single-origin demo server

The built frontend and API can run in one Python process on port 7860. This
package does not provision a hosting account, publish an app or configure DNS.

Prepare the locked backend environment, build the frontend, run
`backend/scripts/setup_omt.py`, and download F1 with `model/_download.py --smoke`.
Then use absolute paths:

```sh
uv run --frozen --directory /absolute/TheArtist-DAW/backend python /absolute/TheArtist-DAW/deploy/serve.py
```

Open `http://localhost:7860`. The launcher requires a valid F1 checkpoint and
ready OMT, serves only `frontend/dist`, and defaults to public-host restrictions
with Meta disabled. It refuses to start if required assets are missing. For
local-only access set `HOST=127.0.0.1`. For a host-managed deployment, configure
HTTPS and access routing with that host; no custom domain is required.

`THEARTIST_SERVE_FRONTEND=1` enables the static mount after all API routes.
Ordinary development keeps the Vite frontend and this switch off. Static files
are mounted using [FastAPI StaticFiles](https://fastapi.tiangolo.com/tutorial/static-files/).
There is no server-side project storage: the browser still owns saved projects.
Public-host mode blocks DAW launch, model warmup, MCP and whole-file Meta reading.
Hosted users download MIDI for their own DAW.

## Optional Meta service

Set the server-side `MODEL_API_KEY` and `THEARTIST_META_ENABLED=1`. Keep
`LLM_PROVIDER=meta` / `muse-spark-1.3` Standard. The [environment template](env.example)
lists request/session/daily/global budgets. Set `THEARTIST_META_LEDGER` and any
separate judge ledger to absolute paths on persistent storage. Restarting with
an empty ledger resets recorded spend; ephemeral storage is unsuitable for
an enabled paid public demo. Session limits are abuse friction, not login or
authentication. One worker owns the local ledger and model cache; do not scale
to independent replicas with independent copies of the same spending budget.

When Meta is off, use **TheArtist only** for a supported vector PDF and
**Genre template** for full form. Meta failures and disabled actions stay visible.
The launcher accepts the same boolean switch spellings as the API.

## Container recipe

```sh
docker build -f /absolute/TheArtist-DAW/deploy/Dockerfile -t theartist-demo /absolute/TheArtist-DAW
docker run --rm -p 7860:7860 theartist-demo
```

The recipe builds assets separately, uses the frozen uv/npm locks, downloads
public F1 and reviewed OMT, and runs as an unprivileged user. API keys and local
model/corpus directories are excluded from the build context. For Meta, supply
server secrets at runtime and mount durable writable storage at `/data`.

**Verification scope:** the single-origin Python server was exercised locally,
including a real 64-bar F1 form in Safari. The container was not built because
Docker was unavailable. The existing Linux dependency lock includes large Torch
and research packages; image size, Linux startup memory, external access and
host resource limits have not been measured. This is a deployment recipe, not
evidence of a live public URL.
