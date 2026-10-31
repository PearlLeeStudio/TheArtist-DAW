# Shared CPU model server

The frontend stays on Cloudflare Pages. The deployment target is **all 18 released
HF model choices: seven base checkpoints and eleven genre LoRA adapters**, served
by one Python service through `/api/*`. It can also call Meta with a server-only secret.
Voyager can use the same API if live generation is added. Separate unrelated apps
can run as separate services on this VM, with shared CPU/RAM/disk capacity.

The Docker recipe downloads all 18 model choices. Startup checks every base
checkpoint, adapter and learned embedding overlay, then loads every model and
rejects a substituted identity. Public-host neural passes are serialized in the
shared process. The Ubuntu CPU server is deployed at
`https://music-api.pearlleestudio.co`; both Artist Pages projects use it.
Every released choice passed actual generation through the hosted API.

## Prepared configuration

- Linux CPU-only Torch from the official PyTorch index, with a separate frozen
  runtime lock. No CUDA, Chroma or sentence-transformers packages in this lock.
- All seven base checkpoints, eleven genre LoRA adapters and local OMT retrieval
  are included. Existing development/training dependencies are unchanged.
- One Python worker; two CPU threads. All 18 choices stay resident on the
  deployed 2-vCPU / 4-GiB host. OMT is ready and Berklee is disabled.
- Docker Engine 29.9.2 and Compose 5.6.1 run the image on Ubuntu 24.04 x64.
  Dependency and public-model layers are cached independently of application code.
  A 4-GiB swap file on the existing disk provides build headroom; no extra VM or
  paid volume is used. Images and build caches also consume disk space.
- HTTPS, persistent writable storage across app replacement, and both Pages
  API routes were verified. Meta keys are supplied at runtime, outside Git and
  the image.

`compose.yaml` runs the app behind Caddy HTTPS. Only ports 80/443 are published;
the Python port stays on the container network. Streaming responses are flushed
without waiting for a full body. [Caddy proxy documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

The named `meta-ledger` volume persists request/cost reservations across container
replacement. Do not remove that volume when updating or disabling Meta. It is
persistent on this VM, not a backup against deleting the VM or its disk.
[Docker volume lifecycle](https://docs.docker.com/engine/storage/volumes/).

## Server setup

For the low-traffic CPU deployment, select **Singapore / SGP1, Ubuntu 24.04 LTS
x64, Basic / Regular, 2 vCPU / 4 GiB RAM / 80 GiB SSD ($24/month)**. Select one
Droplet and the existing SSH public key. Keep **Public IPv4 address enabled**;
extra volumes, automated backups and managed databases are separate optional
products and are not part of this configuration.

Verify a public IPv4 address on the created server before installing the app.
A Private-only Droplet cannot be converted into a standard public Droplet and
does not support the browser console. It would need replacement for this setup.
[Private Droplet limits](https://docs.digitalocean.com/products/droplets/details/limits/#private-droplet-limits).
CPU Droplets are billed for their actual lifetime in seconds, with a minimum
charge of 60 seconds or $0.01, whichever is higher; creating a replacement does
not immediately charge a second full month.
[Droplet billing](https://www.digitalocean.com/pricing/droplets).

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
Both `artist-daw.pearlleestudio.co` and `artist.pearlleestudio.co` should use the
same HTTPS backend and model process. The release Artist has the same API proxy
in its published source; set Production `BACKEND_ORIGIN` separately on both Pages
projects after the model server passes its checks.

The deployed production value on both projects is
`https://music-api.pearlleestudio.co`. Frontend pushes trigger Pages automatically.
The model server's systemd timer independently polls public `TheArtist-DAW/main`
about once a minute. A runtime change builds a candidate while the old service
continues running, then checks startup, all 18 resident choices, actual F1
generation and public HTTPS. Failure restores the previous checkout and image.
Documentation-only pushes do not restart the service. The separate public Artist
release repository does not overwrite this shared backend.

See [automatic deployment](autodeploy.md) for installation, status, retry and
pause commands. Model loading during replacement causes a short API interruption
on this single-server deployment. Pause the timer and wait for any active
deployment before making manual server changes.

For the optional Meta demo, add `MODEL_API_KEY` to the server environment and set
`THEARTIST_META_ENABLED=1` after the storage check. Defaults here cap total spend at
$10, daily global spend at $2 and daily session spend at $2. These are application
limits, not the provider's balance or an automatic credit-expiry detector.

The hosted **Meta only** PDF/image reader is enabled with
`THEARTIST_PUBLIC_META_READER=1`. It uses one Standard Meta call, at most 75 seconds,
8192 completion tokens and $1.35. The session allowance accommodates that worst-case
reservation; the server's $2 daily and $10 total caps remain in place. The separate
flag does not open DAW launch, manual model warmup or MCP. To disable just this
reader, set its flag to `0` and recreate the app; local and bounded assist remain.

To stop using Meta later, set `THEARTIST_META_ENABLED=0`, remove the key from the
server file and recreate the app service:

```sh
docker compose --env-file /srv/theartist.env -f /srv/TheArtist-DAW/deploy/compose.yaml up -d --force-recreate app
```

All 18 HF choices remain usable. Disabled Meta actions report their state. No new
model training or GPU is needed. If another app starts using the same model API,
share this service rather than loading a second catalog merely for that app.

## Hosted verification

- Seven base checkpoints and eleven LoRAs were loaded together. The load probe
  took 27.933 seconds after runtime import and recorded 2,566.4 MiB peak RSS.
- Every model completed an eight-bar HTTPS request with seed 17: **18 requests /
  54 candidates**, all `source=ai`, exact requested `modelUsed`, full bar count.
  Individual request times ranged from 2.688 to 4.769 seconds, including network.
- A 64-bar Classical LoRA request through Artist-DAW returned three full-length
  candidates with the exact model identity in 34.538 seconds (one seed).
- A separate Phase 0 probe completed seeds 17/18/19 at 8/32/64 bars. Median times
  were 2.711 / 9.193 / 18.971 seconds; peak RSS was 2,579.5 MiB. The full repeated
  162-request Linux matrix was stopped after this completed model to prioritize
  checking all 18 through the deployed API. It is not reported as a completed run.
- Both `artist-daw.pearlleestudio.co` and `artist.pearlleestudio.co` returned 18
  loaded models, imported the original one-bar vector-PDF fixture locally,
  returned streamed F1 result frames and produced valid four-track MIDI. Public
  DAW launch and manual warmup returned HTTP 403. Whole-file Meta reading also
  returned 403 before its explicit opt-in; the hosted reader is now enabled as
  described above.
- One hosted 16-bar Meta form completed through Artist-DAW: three Meta calls,
  three generated sections, 34.655 seconds, **$0.01916725**. The three settled
  entries were present in the persistent ledger. A storage marker survived
  app replacement before Meta was enabled.
- The running Python process reached 2,642.3 MiB peak RSS after the API checks;
  the host had about 788 MiB available. This is a low-traffic validation, not a
  maximum-user count or a large-PDF/concurrent-workload capacity guarantee.
- Explicit hosted Meta reading completed the public-domain Mutopia Mozart K.2
  PDF through Artist-DAW: 24 written bars, F major, 3/4, 30.142 seconds and
  $0.02335825. These structural facts do not establish chord accuracy. Two earlier
  attempts on the tiny custom-glyph fixture returned 422 (no usable reading),
  costing $0.01286175 combined; they are not counted as successful imports.

The imported fixture is synthetic and contains one bar. These checks establish
deployment behavior, not general score-reading accuracy or musical preference.
The Voyager website still plays stored audio; live generation and remote MCP
integration remain separate work.

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
operating-system and concurrent-workload headroom. The hosted checks above support
the selected low-traffic 4-GiB configuration within their stated scope.
