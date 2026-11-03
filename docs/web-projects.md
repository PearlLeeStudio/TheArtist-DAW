# Web projects and deployment

The hosted editors, the shared model server and the Voyager extension, with the
deployment pipeline and its limits. The [README](../README.md#live-sites) keeps the summary.

On narrow or portrait screens, header controls sit above the title and the side
panel starts collapsed. Open it with the yellow arrow to use Play or Input; it
fits within the screen. The editor remains primarily a desktop workspace.

| Project | Website | Role |
|---|---|---|
| **TheArtist-DAW — hackathon demo** | [artist-daw.pearlleestudio.co](https://artist-daw.pearlleestudio.co) | AI arrangement workspace: score/sketch → harmony and form → accompaniment → DAW |
| TheArtist — public release | [artist.pearlleestudio.co](https://artist.pearlleestudio.co) | Separately deployed release editor |
| **TheVoyager — project extension** | [voyager.pearlleestudio.co](https://voyager.pearlleestudio.co) | Travel globe, stories and photographs accompanied by generated music |

TheVoyager extends the music service into a travel experience: its Python adapter
requests a song through MCP `build_song` (or explicitly selected REST), then its
own rendering pipeline turns the arrangement into audio. The published Voyager
currently plays pre-generated WAV files; browser-triggered generation is not yet
connected. Voyager's application source and personal travel data are not bundled
in this repository. Its existing travel experience and model assets are separate
from the event contributions recorded in [HACKATHON.md](../HACKATHON.md).

The websites are published on Cloudflare Pages. Both Artist editors share one
Docker backend serving **all 18 released model choices** on DigitalOcean through
`https://music-api.pearlleestudio.co`. Actual generation passed for every model;
API checks on both editor domains passed vector-PDF import, streamed generation
and MIDI export.
Bounded Meta planning is enabled with a server-only key.
See [deployment, measurements and limits](../deploy/vps.md).
Public Git pushes update Pages automatically. The shared model server also polls
this repository's `main` branch and deploys runtime changes with health checks
and rollback; see [automatic deployment](../deploy/autodeploy.md).

Hosted **Open in Logic Pro** uses the [local Mac bridge](midi-input.md#open-a-hosted-score-in-logic-pro)
to deliver the generated MIDI to the user's Mac. The cloud server does not launch
desktop applications. Download MIDI remains available without the helper.

```text
Local edit → commit + push → public TheArtist-DAW/main
  ├─ Cloudflare Pages build → artist-daw.pearlleestudio.co
  └─ DigitalOcean checks Git → Docker build + health checks → music-api.pearlleestudio.co

Public TheArtist/main → Cloudflare Pages build → artist.pearlleestudio.co
Both Artist websites → /api/* → the shared model API above
```

Docker packages the server code, libraries and all 18 model choices. The API key
and persistent cost ledger stay outside the image. The server checks Git about
once a minute; documentation-only and frontend-only pushes do not restart it. Runtime replacement
briefly interrupts the API while models load. The release frontend follows its
own reviewed public snapshot; hackathon code is not automatically merged into it.

The Docker image includes MCP code, but public-host mode does not expose its MCP
endpoint. [Voyager's API/MCP deployment path](mcp.md#voyager-on-a-shared-host)
distinguishes the existing adapter from the remaining hosted integration.

## From Docker to the public domains

Use the sequence below for a new deployment. The domain names describe the
existing installation; use domains you control for a separate deployment.
These steps provision application services on an existing host, not a hosting
account or a domain purchase. The [local Docker quick start](../README.md#getting-started)
runs the same app without DNS or Pages.

### 1. Prepare the Linux host and runtime settings

The deployed host is Ubuntu 24.04 x64 with 2 vCPUs, 4 GiB RAM and 4 GiB swap.
Install Git and Docker Engine with the Compose plugin using
[Docker's Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
Run the server commands as its administrator:

```sh
git clone https://github.com/PearlLeeStudio/TheArtist-DAW.git /srv/TheArtist-DAW
install -m 600 /srv/TheArtist-DAW/deploy/vps.env.example /srv/theartist.env
```

Edit `/srv/theartist.env` on the server. Set `API_HOST` to the API hostname,
without a scheme or path. The template starts with Meta off. To enable it, set
`MODEL_API_KEY`, `THEARTIST_META_ENABLED=1` and, for original-file reading,
`THEARTIST_PUBLIC_META_READER=1`. Keep `LLM_PROVIDER=meta` and
`LLM_MODEL=muse-spark-1.3`. The file stays outside Git and is injected at runtime;
neither Docker build arguments nor Pages receive the key. Keep the persistent
ledger and the existing budget configuration described in the
[server guide](../deploy/README.md#optional-meta-service).

### 2. Point the API domain at Caddy

Create a DNS **A** record for `music-api.pearlleestudio.co` pointing at the
host's public IPv4 address. For a new installation, use DNS-only routing while
verifying the direct Caddy endpoint. An AAAA record should exist only if the
same service is reachable over that IPv6 address. Allow inbound TCP **80 and
443** through the host/network firewall; keep the application port private.

Set `API_HOST=music-api.pearlleestudio.co` in the server environment file. The
[Caddyfile](../deploy/Caddyfile) uses it as the HTTPS site name and proxies to
`app:7860`. Caddy obtains and renews certificates and redirects HTTP to HTTPS
when DNS and challenge connectivity are correct.
[Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).

### 3. Build and start the complete model service

```sh
docker compose --env-file /srv/theartist.env -f /srv/TheArtist-DAW/deploy/compose.yaml config --quiet
docker compose --env-file /srv/theartist.env -f /srv/TheArtist-DAW/deploy/compose.yaml up -d --build
docker compose --env-file /srv/theartist.env -f /srv/TheArtist-DAW/deploy/compose.yaml ps
docker compose --env-file /srv/theartist.env -f /srv/TheArtist-DAW/deploy/compose.yaml logs --tail 60 app
curl --fail --user-agent TheArtistDeploymentCheck/1.0 https://music-api.pearlleestudio.co/api/health
```

The [Dockerfile](../deploy/Dockerfile) builds the frontend with pinned Node and
the npm lock, installs Python 3.12 with the separate frozen CPU runtime lock,
downloads all 18 model choices and prepares the reviewed OMT subset. Its model
download does **not** use `--smoke`. The unprivileged app starts one worker and
validates every model's identity and OMT readiness. The initial build needs
network access; later application edits reuse dependency/model layers.

Compose publishes only Caddy's 80/443 ports. The `meta-ledger` volume holds `/data`
across application replacement; `caddy-data` and `caddy-config` preserve HTTPS
state. Updating the app must retain these volumes. The Meta key is runtime
configuration, not an image layer. [compose.yaml](../deploy/compose.yaml).

### 4. Build the frontend and attach its domain

Create a Git-connected Cloudflare Pages project for
`PearlLeeStudio/TheArtist-DAW` with:

| Setting | Value |
|---|---|
| Production branch | `main` |
| Root directory | `frontend` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Build variable | `NODE_VERSION=26.13.0` |
| Production runtime variable | `BACKEND_ORIGIN=https://music-api.pearlleestudio.co` |
| Function failure behavior | **Fail closed** |
| Custom domain | `artist-daw.pearlleestudio.co` |

Save the runtime variable and redeploy. In the Pages project's **Custom domains**
section, add the frontend hostname and complete its DNS association. Associating
the hostname with Pages is required; a CNAME record alone does not register the
site. [Cloudflare custom domains](https://developers.cloudflare.com/pages/configuration/custom-domains/).

The built [worker](../frontend/public/_worker.js) handles `/api` and `/api/*`,
using an HTTPS `BACKEND_ORIGIN` with no path. Other requests serve static assets.
It streams API responses and forwards `X-TheArtist-Session`, but not browser
cookies or Authorization headers. A missing/invalid origin returns an explicit
503; upstream failure or an unexpected redirect returns 502. This is the
[Pages advanced-mode worker](https://developers.cloudflare.com/pages/functions/advanced-mode/),
not model execution inside Cloudflare.

For the public-release editor, create a separate Pages project connected to
`PearlLeeStudio/TheArtist`, attach `artist.pearlleestudio.co`, and set the same
Production `BACKEND_ORIGIN` there. Its frontend release remains independent of
the hackathon repo. The backend follows only `TheArtist-DAW/main`.

### 5. Verify the complete route

```sh
curl --fail --user-agent TheArtistDeploymentCheck/1.0 https://artist-daw.pearlleestudio.co/api/health
curl --fail --user-agent TheArtistDeploymentCheck/1.0 https://artist-daw.pearlleestudio.co/api/models/list
curl --fail --user-agent TheArtistDeploymentCheck/1.0 https://artist-daw.pearlleestudio.co/api/capabilities
curl --fail --user-agent TheArtistDeploymentCheck/1.0 --header 'Content-Type: application/json' --data '{"key":"C major","genre":"jazz","sectionType":"verse","chordCount":16,"modelKey":"ft_f1","seed":17}' https://artist-daw.pearlleestudio.co/api/generate/section
```

Expect health `ok`, 18 available models, OMT `ready`, Berklee `disabled`, and
generation with `source: "ai"`, `modelUsed: "ft_f1"`, eight bars and three
suggestions. This generation uses the own model and makes no paid Meta call.
Repeat the route check through the release domain when deploying that project.

Open the frontend domain in a browser and check a supported vector-PDF import,
streamed generation, playback and MIDI download. If Meta was enabled, check
its capability state and deliberately exercise the opted-in features; those
calls consume the configured account's credit. Confirm their source/request
details, including explicit local recovery after a failed Meta reading. API
health alone proves neither model generation nor browser audio.

### 6. Install automatic updates

Follow [the controller installation](../deploy/autodeploy.md#install-on-the-model-server)
to install the controller and systemd units outside the checkout. The timer
checks public Git about a minute after each completed check. No GitHub deployment
token is needed. It ignores documentation/frontend-only changes for model-server
restart purposes; Pages builds frontend changes independently.

For a runtime change, the controller builds while the old app serves, checks
offline import and OMT, switches the app, waits for health, checks all 18 model
identities, runs actual F1 generation and verifies public HTTPS. Failure retains
or restores the previous image/checkout. The single-host switch can briefly
interrupt requests while models load. The installed controller does not update
itself from Git; controller/unit changes require a separate administrator install.

## Deployment file map

| File | Responsibility |
|---|---|
| [Dockerfile](../deploy/Dockerfile), [CPU runtime lock](../deploy/runtime/uv.lock) | Reproducible frontend/runtime build, full model catalog and OMT preparation |
| [.dockerignore](../.dockerignore) | Exclude local keys, weights, corpora, caches and unrelated artifacts from the build context |
| [serve.py](../deploy/serve.py), [readiness checks](../backend/app/services/serving_readiness.py) | Complete-catalog startup and single-process UI/API serving |
| [compose.yaml](../deploy/compose.yaml), [Caddyfile](../deploy/Caddyfile) | Service wiring, internal app port, HTTPS and persistent volumes |
| [vps.env.example](../deploy/vps.env.example), [env.example](../deploy/env.example) | Server configuration templates; no real credentials |
| [worker](../frontend/public/_worker.js), [routes](../frontend/public/_routes.json) | Same-origin Pages API forwarding and route scope |
| [autodeploy.py](../deploy/autodeploy.py), [service](../deploy/theartist-deploy.service), [timer](../deploy/theartist-deploy.timer) | Public Git polling, build, acceptance checks and rollback |

Recorded host measurements and their limits are in [the server report](../deploy/vps.md).
The low-traffic checks do not measure maximum simultaneous users, general PDF
accuracy, or musical quality. [Model comparison evidence](model-comparison.md)
keeps those component evaluations separate from deployment acceptance.
