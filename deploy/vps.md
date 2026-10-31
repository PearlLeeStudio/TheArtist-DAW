# Shared CPU model server

The frontend stays on Cloudflare Pages. One Python service loads the public HF F1
checkpoint and serves `/api/*`; it can also call Meta with a server-only secret.
Voyager can use the same API if live generation is added. Separate unrelated apps
can run as separate services on this VM, with shared CPU/RAM/disk capacity.

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

## Hosting decision still pending

A proposed starting VM is DigitalOcean Basic, 2 vCPU / 4 GiB / 80 GiB SSD,
**$0.03571/hour, capped at $24/month**, before applicable taxes and optional add-ons.
[Official pricing](https://www.digitalocean.com/pricing/droplets).
This is a proposed allocation; no VM/account/subscription was created. Keep Meta
API usage separate from the hosting bill. Validate capacity on the target before
claiming the VM can handle a given concurrent workload.

Hugging Face is also possible, but Docker Spaces require a paid account plan and
their default disk is ephemeral. A paid Meta cost ledger needs appropriate durable
storage; a mounted object-storage bucket must be checked for the ledger's locking
and atomic-replace requirements before adoption.
[Spaces plans](https://huggingface.co/docs/hub/spaces-overview),
[Space storage](https://huggingface.co/docs/hub/spaces-storage).
