"""Server-side public Git deployment; no GitHub token or inbound deploy endpoint.

Install this controller outside the checkout. Its own updates require an explicit
administrator install; application commits are deployed by the systemd timer.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import re
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

REPO = "/srv/TheArtist-DAW"
ORIGIN = "https://github.com/PearlLeeStudio/TheArtist-DAW.git"
IMAGE = "theartist-model-server-app:latest"
CANDIDATE = "theartist-model-server-app:candidate"
PREVIOUS = "theartist-model-server-app:previous"
STATE_DIR = Path("/var/lib/theartist-deploy")
STATE_FILE = Path("/var/lib/theartist-deploy/state.json")
PENDING_FILE = Path("/var/lib/theartist-deploy/state.pending")
LOCK_FILE = Path("/var/lib/theartist-deploy/lock")

# Runs inside the already warmed container; does not import a second model catalog.
SMOKE = r'''
import json
from urllib.request import Request, urlopen
def get(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request("http://127.0.0.1:7860" + path, data=data,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=90) as response:
        return json.load(response)
expected = {"phase0", "ft_f1", "ft_f1_v2", "ft_f2", "ft_f3", "ft_f4", "ft_f5"}
expected.update("ft_f1_lora_" + genre for genre in (
    "country", "funk", "gospel", "rnb_soul", "hip_hop", "electronic",
    "folk", "classical", "rock", "blues", "bossa"))
assert get("/api/health")["status"] == "ok"
catalog = get("/api/models/list")["models"]
assert {row["key"] for row in catalog} == expected
assert all(row["available"] for row in catalog)
status = get("/api/models/status")
assert status["torch_available"] and set(status["models"]) == expected
assert all(status["models"].values())
result = get("/api/generate/section", {
    "key": "C major", "genre": "jazz", "sectionType": "verse",
    "chordCount": 16, "modelKey": "ft_f1", "seed": 17})
assert result["source"] == "ai" and result["modelUsed"] == "ft_f1"
assert result["bars"] == 8 and len(result["suggestions"]) == 3
assert all(len(row["chords"]) == 8 for row in result["suggestions"])
print("18 models resident; F1 generation passed; no paid Meta calls")
'''


def runtime_changed(paths: list[str]) -> bool:
    """Default to deploying unknown files; skip only documentation/test changes."""
    return any(not (
        path.endswith((".md", ".rst"))
        or path in {"LICENSE", "AGENTS.md", ".gitignore"}
        or path.startswith(("docs/", "backend/tests/", "frontend/tests/", ".github/"))
    ) for path in paths)


def command(args: list[str], *, timeout=120, capture=True, umask=-1) -> str:
    result = subprocess.run(args, check=True, timeout=timeout, text=True,
                            stdout=subprocess.PIPE if capture else None, umask=umask)
    return result.stdout.strip() if capture else ""


class Host:
    def git(self, *args) -> str:
        # The controller's private state uses 0077, but this public checkout must
        # remain readable by the unprivileged container user after each update.
        return command(["git", "-C", REPO, *args], umask=0o022)

    def inspect(self) -> tuple[str, str]:
        if self.git("remote", "get-url", "origin") != ORIGIN:
            raise RuntimeError("Refusing an unexpected repository origin")
        if self.git("status", "--porcelain"):
            raise RuntimeError("Refusing to overwrite a dirty server checkout")
        self.git("fetch", "--no-tags", "origin",
                 "+refs/heads/main:refs/remotes/origin/main")
        current = self.git("rev-parse", "HEAD")
        target = self.git("rev-parse", "refs/remotes/origin/main")
        if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (current, target)):
            raise RuntimeError("Invalid Git revision")
        return current, target

    def changes(self, current, target):
        return self.git("diff", "--name-only", "--no-renames", current, target).splitlines()

    def checkout(self, revision):
        self.git("checkout", "--detach", revision)

    def container(self):
        container = self.compose("ps", "-q", "app")
        if not container or "\n" in container:
            raise RuntimeError("Expected one running model service")
        return container

    def current_image(self):
        return command(["docker", "inspect", "--format", "{{.Image}}", self.container()])

    def tag(self, source, destination):
        command(["docker", "image", "tag", source, destination])

    def build(self, revision):
        command(["docker", "build", "--label", "org.opencontainers.image.revision=" + revision,
                 "--tag", CANDIDATE, "--file", "/srv/TheArtist-DAW/deploy/Dockerfile", REPO],
                timeout=2400, capture=False)
        # Import as the image's actual runtime user before stopping the old app.
        # No network, secrets, paid calls or second in-memory model catalog.
        command(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python", CANDIDATE,
                 "-c", "import sys; sys.path.insert(0, '/app/backend'); import app.main; "
                 "from app.services.contracts import capabilities; "
                 "assert capabilities().data['rag']['sources'] == {'omt': 'ready', 'berklee': 'disabled'}; "
                 "print('Candidate runtime import and OMT assets readable')"],
                timeout=180, capture=False)

    def diagnostics(self):
        self.compose("logs", "--no-color", "--tail", "60", "app", capture=False)

    def compose(self, *args, timeout=360, capture=True):
        return command(["docker", "compose", "--env-file", "/srv/theartist.env",
                        "-f", "/srv/TheArtist-DAW/deploy/compose.yaml", *args],
                       timeout=timeout, capture=capture)

    def start(self):
        self.compose("up", "-d", "--no-build", "--pull", "never", "--wait",
                     "--wait-timeout", "240", "app", capture=False)
        # Recreate the proxy to refresh its read-only Caddyfile mount and app DNS.
        self.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never",
                     "--force-recreate", "https", capture=False)

    def smoke(self):
        command(["docker", "exec", self.container(), "python", "-c", SMOKE],
                timeout=120, capture=False)
        host = next((line.split("=", 1)[1].strip() for line in
                     Path("/srv/theartist.env").read_text().splitlines()
                     if line.startswith("API_HOST=")), "")
        if not re.fullmatch(r"[a-zA-Z0-9.-]+", host):
            raise RuntimeError("API_HOST must be a DNS name")
        request = Request("https://" + host + "/api/health",
                          headers={"User-Agent": "TheArtistDeploymentCheck/1.0"})
        with urlopen(request, timeout=30) as response:
            if json.load(response).get("status") != "ok":
                raise RuntimeError("Public HTTPS health check failed")


def save_state(state):
    PENDING_FILE.write_text(json.dumps(state, indent=2) + "\n")
    PENDING_FILE.replace(STATE_FILE)


def rollback(host, state, save):
    transaction = state["pending"]
    host.checkout(transaction["checkout"])
    if transaction["phase"] == "switching":
        host.tag(transaction["image"], IMAGE)
        host.start()
        host.smoke()
    state["failed_revision"] = transaction["target"]
    state.pop("pending")
    save(state)
    print("Previous service retained/restored; rejected " + state["failed_revision"], flush=True)


def run_once(host, state, save, *, retry=False):
    # A killed process or host restart must finish recovery before handling new work.
    if "pending" in state:
        rollback(host, state, save)
    current, target = host.inspect()
    if not state:
        state.update(deployed_revision=current, observed_revision=current)
        save(state)
    if state.get("failed_revision") == target and not retry:
        return "failed-revision-skipped"
    if current == target and not retry:
        return "unchanged"
    if not retry and not runtime_changed(host.changes(current, target)):
        host.checkout(target)
        state["observed_revision"] = target
        state.pop("failed_revision", None)
        save(state)
        print("Documentation-only push: " + target + "; service unchanged", flush=True)
        return "documentation-only"
    old_image = host.current_image()
    host.tag(old_image, PREVIOUS)
    state["pending"] = dict(checkout=current, image=old_image, target=target, phase="building")
    save(state)
    try:
        host.checkout(target)
        host.build(target)
        state["pending"]["phase"] = "switching"
        save(state)
        host.tag(CANDIDATE, IMAGE)
        host.start()
        host.smoke()
    except Exception:
        if state["pending"]["phase"] == "switching":
            try:
                host.diagnostics()
            except Exception:
                pass  # Diagnostic collection must never prevent recovery.
        rollback(host, state, save)
        raise
    state.update(deployed_revision=target, observed_revision=target)
    state.pop("pending")
    state.pop("failed_revision", None)
    save(state)
    print("Deployed " + target + "; HTTPS and all 18 models checked", flush=True)
    return "deployed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry", action="store_true", help="Retry the current upstream revision once")
    args = parser.parse_args()
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with LOCK_FILE.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another deployment is already running")
            return
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        run_once(Host(), state, save_state, retry=args.retry)


if __name__ == "__main__":
    main()
