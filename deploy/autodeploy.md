# Automatic model-server deployment

The server polls the public `PearlLeeStudio/TheArtist-DAW` **main** branch about
once a minute. It uses anonymous HTTPS Git reads; no GitHub deployment token,
SSH secret in Actions, webhook, or additional paid service is required.
Both Artist frontends share this backend. The separate `TheArtist` release
repository updates its own Pages frontend, not this shared backend.

```text
Local changes → commit + push to public GitHub
  ├─ Cloudflare Pages build → Artist frontend domain
  └─ server timer → Docker build → model API → both Artist frontends
```

The timer waits 60 seconds after each completed check or deployment, with up to
five seconds of scheduling tolerance. Builds take additional time. Documentation
and backend-test-only changes advance the checkout without restarting the API.
Unknown changed files trigger a build. Dependencies and model downloads occupy
cached Docker layers, separate from application code.

A candidate builds while the current container continues serving. Before replacing
anything, an offline container imports the application as its actual runtime user
and checks OMT asset readability. Public Git checkouts use readable source-file
permissions; private deployment state retains the service's restrictive mask.
The controller
then replaces the app, waits up to 240 seconds for health, refreshes Caddy, checks
all 18 resident model identities, generates three eight-bar F1 candidates, and
checks public HTTPS. The generation check makes no paid Meta calls. The one-worker
server has a short API interruption during replacement and model loading; this
is not a zero-downtime deployment.

Build or candidate-import failure retains the running app. Startup, generation or HTTPS failure
restores the previous checkout and image and checks that service again. A failed
revision waits for a new push or explicit retry rather than rebuilding forever.
A persistent transaction also supports recovery after an interrupted controller.
The API key stays in `/srv/theartist.env`; named volumes, including the Meta cost
ledger, are never removed by deployment. Git fetch failure or a dirty checkout
stops the check without overwriting local changes.

## Install on the model server

After the initial [server setup](vps.md), install the reviewed controller outside
the checkout. These commands run on the Ubuntu server as its administrator:

```sh
install -d -m 755 /usr/local/lib/theartist
install -m 755 /srv/TheArtist-DAW/deploy/autodeploy.py /usr/local/lib/theartist/autodeploy.py
install -m 644 /srv/TheArtist-DAW/deploy/theartist-deploy.service /etc/systemd/system/theartist-deploy.service
install -m 644 /srv/TheArtist-DAW/deploy/theartist-deploy.timer /etc/systemd/system/theartist-deploy.timer
systemctl daemon-reload
systemctl enable --now theartist-deploy.timer
```

The installed controller and unit files deliberately do not replace themselves
from a push. Reinstall those three reviewed files explicitly when changing the
deployment mechanism. Runtime files, Dockerfile, Compose and Caddy configuration
are picked up automatically. The deployment source is fixed to the public DAW
repository; do not point the second Artist repository at the same server checkout.

On the 4-GiB host, a 4-GiB swap file on the existing disk supplies build headroom.
It adds no RAM or GPU and does not require a paid storage add-on. Heavy concurrent
work can still be slow. Check free disk space as images and build caches accumulate;
never remove the ledger volume to reclaim space.

## Inspect, retry or pause

```sh
systemctl is-enabled theartist-deploy.timer
systemctl list-timers theartist-deploy.timer --no-pager
journalctl -u theartist-deploy.service -n 60 --no-pager
cat /var/lib/theartist-deploy/state.json
docker compose --env-file /srv/theartist.env -f /srv/TheArtist-DAW/deploy/compose.yaml ps
```

State distinguishes `observed_revision` (including documentation pushes) from
`deployed_revision` (the running application revision). A failed or in-progress
transaction is visible there. The previous image is tagged
`theartist-model-server-app:previous`. Only one controller may run at a time.

```sh
# Check now using the same installed controller.
systemctl start theartist-deploy.service
# Retry a rejected revision after fixing an external dependency.
/usr/bin/python3 /usr/local/lib/theartist/autodeploy.py --retry
# Pause future automatic deployments; this does not stop the running app.
systemctl disable --now theartist-deploy.timer
```

Pausing the timer does not cancel a deployment already running. Let that operation
finish before making manual server changes. Resume with
`systemctl enable --now theartist-deploy.timer`.

## Verification

The installed timer detected public commit `925759b`, built the candidate while
both existing domain APIs remained healthy, and switched the running image to
that revision. All 18 models were resident, actual F1 generation passed, and
public HTTPS was healthy. The persistent storage marker survived and the Meta
ledger checksum was unchanged. An earlier documentation-only push advanced the
observed revision without replacing the app.

Ten automated deployment tests cover failed builds, unhealthy startup, generation
failure, rollback failure, interrupted-switch recovery, retry suppression,
documentation-only changes and dirty checkout refusal. Failure recovery was
tested with controlled doubles, not by deliberately breaking the production
service. Frontend build/lint and backend import also pass; the existing large
frontend bundle warning remains. No paid Meta call was made for these checks.

[systemd timer behavior](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html),
[Compose health waiting](https://docs.docker.com/reference/cli/docker/compose/up/),
[Docker layer caching](https://docs.docker.com/build/cache/optimize/).
