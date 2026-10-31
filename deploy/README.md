# Single-origin demo server

The built frontend and API can run in one Python process on port 7860. This
package does not provision a hosting account, publish an app or configure DNS.

Prepare the locked backend environment, build the frontend, run
`backend/scripts/setup_omt.py`, and download all 18 model choices with `model/_download.py`
(without `--smoke`).
Then use absolute paths:

```sh
uv run --frozen --directory /absolute/TheArtist-DAW/backend python /absolute/TheArtist-DAW/deploy/serve.py
```

Open `http://localhost:7860`. The launcher requires every released base checkpoint,
LoRA adapter and learned embedding overlay, verifies each loaded model's identity and
ready OMT, serves only `frontend/dist`, and defaults to public-host restrictions
with Meta disabled. It refuses to start if required assets are missing. For
local-only access set `HOST=127.0.0.1`. For a host-managed deployment, configure
HTTPS and access routing with that host; no custom domain is required.

`THEARTIST_SERVE_FRONTEND=1` enables the static mount after all API routes.
Ordinary development keeps the Vite frontend and this switch off. Static files
are mounted using [FastAPI StaticFiles](https://fastapi.tiangolo.com/tutorial/static-files/).
There is no server-side project storage: the browser still owns saved projects.
Public-host mode blocks DAW launch, model warmup and MCP. Whole-file Meta reading
also requires `THEARTIST_PUBLIC_META_READER=1`; the hosted Artist service enables
it while preserving the one-call timeout and all spend limits.
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

The recipe builds assets separately, uses the frozen CPU runtime/npm locks, downloads
all seven base checkpoints, eleven genre adapters and reviewed OMT, and runs as an unprivileged user. API keys and local
model/corpus directories are excluded from the build context. For Meta, supply
server secrets at runtime and mount durable writable storage at `/data`.

**Verification scope:** the image was built and run on Ubuntu 24.04 x64 with
2 shared vCPUs and 4 GiB RAM. All 18 models remain loaded in one worker; each
passed an eight-bar HTTPS generation with three candidates and the exact model
identity. API checks on both Artist domains passed a synthetic vector-PDF import,
streamed F1 generation and four-track MIDI export. A hosted Meta form completed with a
persistent cost record. These are functional deployment checks, not a listening
evaluation or a concurrent-user capacity guarantee.
The separate `deploy/runtime` lock selects Linux CPU Torch and excludes unused
embedding/vector research dependencies.
See the [shared CPU server recipe](vps.md) for HTTPS, persistent cost storage and
disabling Meta while retaining the full HF catalog. Public-host neural generation
is serialized across clients to bound concurrent working memory. `catalog_probe.py`
keeps every model resident and exercises actual generation without Meta calls.
Both public editors are connected to the deployed shared server. The local
development setup remains separate.
The server's [automatic deployment controller](autodeploy.md) follows the public
DAW `main` branch, builds runtime changes, checks all 18 resident models and actual
generation, and restores the previous image if deployment fails. Large model and
dependency layers are cached independently of application edits.
