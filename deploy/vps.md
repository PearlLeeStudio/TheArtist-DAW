# Shared CPU model server

The frontend stays on Cloudflare Pages. The deployment target is **all 18 released
HF model choices: seven base checkpoints and eleven genre LoRA adapters**, served
by one Python service through `/api/*`. It can also call Meta with a server-only secret.
Voyager can use the same API if live generation is added. Separate unrelated apps
can run as separate services on this VM, with shared CPU/RAM/disk capacity.

**The checked-in Docker recipe still downloads and checks only F1.** Before a full
deployment, remove the download's `--smoke` restriction, validate every requested
model without fallback, and verify all 18 choices through the hosted API. The
single-model recipe is not completion of the full-catalog deployment.

## Prepared configuration

- Linux CPU-only Torch from the official PyTorch index, with a separate frozen
  runtime lock. No CUDA, Chroma or sentence-transformers packages in this lock.
- F1, LoRA support and local OMT retrieval remain available; the image downloads
  only F1 by default. Existing development/training dependencies are unchanged.
- One Python worker; two CPU threads. Three eight-bar F1 runs, OMT readiness,
  `/api/health` and the built frontend passed in a fresh local runtime environment.
- The local Mac probe used 880.2 MiB peak process memory and a 0.206 s median for
  eight-bar generation after model loading. These are **not Linux/cloud capacity
  or latency measurements**. No paid Meta calls were made by the probe.
- Docker is unavailable locally, so image build, Compose execution, Linux memory,
  TLS issuance and durable-volume behavior still require the actual server check.

`compose.yaml` runs the app behind Caddy HTTPS. Only ports 80/443 are published;
the Python port stays on the container network. Streaming responses are flushed
without waiting for a full body. [Caddy proxy documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

The named `meta-ledger` volume persists request/cost reservations across container
replacement. Do not remove that volume when updating or disabling Meta. It is
persistent on this VM, not a backup against deleting the VM or its disk.
[Docker volume lifecycle](https://docs.docker.com/engine/storage/volumes/).

## Server setup

The recipe expects the public repository at `/srv/TheArtist-DAW`, Docker with
Compose, and a server DNS name supplied through `API_HOST`. Copy `vps.env.example`
to `/srv/theartist.env`, outside the checkout, and restrict that file to the server
administrator. The template has no key and starts with Meta off.

```sh
docker compose --env-file /srv/theartist.env -f /srv/TheArtist-DAW/deploy/compose.yaml config --quiet
docker compose --env-file /srv/theartist.env -f /srv/TheArtist-DAW/deploy/compose.yaml up -d --build
```

After TLS and `/api/health` work, set Cloudflare Pages Production `BACKEND_ORIGIN`
to the server's HTTPS origin and redeploy. Verify actual generation, Import failure
boundaries, streamed results and MIDI download through the custom frontend domain.
The release Artist frontend needs its own compatible API forwarding change before
it can use this host; its current static deployment does not include that change.

For the optional Meta demo, add `MODEL_API_KEY` to the server environment and set
`THEARTIST_META_ENABLED=1` after the storage check. Defaults here cap total spend at
$10, daily global spend at $2 and daily session spend at $1. These are application
limits, not the provider's balance or an automatic credit-expiry detector.

To stop using Meta later, set `THEARTIST_META_ENABLED=0`, remove the key from the
server file and recreate the app service:

```sh
docker compose --env-file /srv/theartist.env -f /srv/TheArtist-DAW/deploy/compose.yaml up -d --force-recreate app
```

The HF model remains usable. Disabled Meta actions report their state. No new
model training or GPU is needed. If another app starts using the same model API,
share this service rather than loading a second copy of F1 merely for that app.

## Full-catalog capacity and hosting options

A local macOS probe in the frozen CPU runtime held **all 18 models resident** in
one process with two Torch threads. Each model generated 8, 32 and 64 bars at
seeds 17, 18 and 19: **162 requests / 486 candidates**. Every response reported
`source=ai`, the exact requested `modelUsed`, three candidates and the full length.
There were no model substitutions or paid Meta calls. OMT was ready and Berklee
disabled; health and built-frontend requests both returned HTTP 200.

- Process peak: **2,553.9 MiB (2.49 GiB)**, including all models and generation.
- Loading all models: 2.937 seconds from local storage after runtime import.
- Per-model median generation time: 8 bars 0.168–0.254 seconds; 64 bars
  1.329–2.165 seconds, each request producing three candidates.
- Checkpoint/adapter weight files: 2,190,922,173 bytes. Loaded parameters occupy
  about 1.75 GiB in float32; the process total includes runtime and working memory.

These are **local sequential CPU measurements**, not Linux, DigitalOcean, GPU,
concurrency, PDF-import peak-memory or end-to-end network measurements. Model
availability does not require executing all 18 models for every request. No GPU
speedup or maximum simultaneous-user count has been measured.

| Option | Resources | Hosting price | Intended use |
|---|---|---|---|
| Basic / Regular / Bundled | 2 shared vCPU, 4 GiB RAM, 80 GiB SSD | $0.03571/hour, capped at $24/month | Low-traffic starting candidate; verify Linux memory and bound generation concurrency before opening access |
| Basic / Regular / Bundled | 4 shared vCPU, 8 GiB RAM, 160 GiB SSD | $0.07143/hour, capped at $48/month | More memory headroom for PDF work and additional services |
| CPU-Optimized / Regular | 4 dedicated vCPU, 8 GiB RAM, 50 GiB SSD | $0.125/hour, capped at $84/month | More predictable CPU allocation if sustained load warrants it |
| RTX 4000 Ada GPU | 20 GB VRAM, 8 vCPU, 32 GiB RAM, 500 GiB disk | $0.76/hour; $547.20 for 30 continuous days | Optional GPU deployment; requires a CUDA runtime and target measurement |

[CPU pricing](https://www.digitalocean.com/pricing/droplets),
[GPU pricing](https://www.digitalocean.com/pricing/gpu-droplets).
Prices exclude applicable taxes, optional add-ons and Meta API usage. The GPU
estimate is 720 hours, not a monthly cap; powered-off GPU Droplets remain billable
until destroyed. The existing runtime lock uses CPU Torch and will not use a GPU
merely because the VM has one.

For low traffic, first validate the $24 CPU configuration with the full catalog,
bounded generation concurrency, PDF import and HTTPS running together. Move to
8 GiB only if target measurements or additional services need the headroom. The
2.49 GiB process result alone is not proof that a 4 GiB Linux VM has sufficient
operating-system and concurrent-workload headroom. No VM has been provisioned.
