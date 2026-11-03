"""Reconstruct the app in a separate dependency checkout, verifying all deltas."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--core-source", help="Optional local mirror for offline reconstruction")
    parser.add_argument("--install", action="store_true", help="Install locked dependencies and build the frontend")
    parser.add_argument("--prepare-assets", action="store_true", help="Download F1 and reviewed OMT; requires --install")
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    if not args.target.is_absolute() or args.target.exists() or args.target.resolve().is_relative_to(package):
        parser.error("Use a new absolute target outside this submission directory")
    if args.prepare_assets and not args.install:
        parser.error("--prepare-assets requires --install")
    manifest = json.loads((package / "manifest.json").read_text())
    patch = package / "changes.patch"
    if manifest["version"] != 2 or hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["patchSha256"]:
        raise SystemExit("Invalid manifest or patch checksum")
    for name in manifest["files"]:
        if Path(name).is_absolute() or ".." in Path(name).parts or ".git" in Path(name).parts:
            raise SystemExit("Invalid manifest path")
    materialized = manifest["materializedFiles"]
    for name, entry in materialized.items():
        if name not in manifest["files"] or entry["mode"] not in {"100644", "100755"}:
            raise SystemExit("Invalid materialized file entry")
        source = package / name
        if source.is_symlink() or not source.resolve().is_relative_to(package):
            raise SystemExit(f"Invalid contribution file: {name}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["files"][name]:
            raise SystemExit(f"Contribution file checksum mismatch: {name}")
    run("git", "clone", "--no-checkout", args.core_source or manifest["core"]["repository"], args.target)
    run("git", "-C", args.target, "checkout", "--detach", manifest["core"]["commit"])
    tree = subprocess.check_output(["git", "-C", str(args.target), "rev-parse", "HEAD^{tree}"]).decode().strip()
    if tree != manifest["core"]["tree"]:
        raise SystemExit("Core tree checksum differs from the declared baseline")
    run("git", "-C", args.target, "apply", "--check", patch)
    run("git", "-C", args.target, "apply", patch)
    for name, entry in materialized.items():
        destination = args.target / name
        if destination.exists() != entry["replacesCore"]:
            raise SystemExit(f"Unexpected core/patch collision: {name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((package / name).read_bytes())
        destination.chmod(0o755 if entry["mode"] == "100755" else 0o644)
    for name, checksum in manifest["files"].items():
        file = args.target / name
        actual = hashlib.sha256(file.read_bytes()).hexdigest() if file.exists() else None
        if actual != checksum:
            raise SystemExit(f"Reconstructed file mismatch: {name}")
    print(f"Verified {len(manifest['files'])} changed paths against the manifest", flush=True)
    if args.install:
        backend, frontend = args.target / "backend", args.target / "frontend"
        run("uv", "sync", "--frozen", "--python", "3.12", "--directory", backend)
        run("npm", "--prefix", frontend, "ci")
        run("npm", "--prefix", frontend, "run", "build")
        run("uv", "run", "--frozen", "--directory", backend, "python", "-c", "import app.main; print('app import: ok')")
        if args.prepare_assets:
            for script in (backend / "scripts/setup_omt.py", args.target / "model/_download.py"):
                run("uv", "run", "--frozen", "--directory", backend, "python", script,
                    *(["--smoke"] if script.name == "_download.py" else []))
    print("Reconstruction complete. No pre-event checkout or history was added to the submission directory.")


if __name__ == "__main__":
    main()
