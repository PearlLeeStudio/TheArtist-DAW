"""Publish browsable event files and a patch against a separately acquired core.

The output contains no pre-event checkout or git history. Provenance candidates
are review evidence, not an assertion that every added line is newly authored.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# The pre-event core: this repository's public `baseline` tag, which holds the public TheArtist snapshot
# f043e53 unchanged (same tree). The public TheArtist repository keeps only its latest
# snapshot, so that commit is no longer served there.
CORE_REPOSITORY = "https://github.com/PearlLeeStudio/TheArtist-DAW.git"
CORE_COMMIT = "852204b7b3ba1a610d623c84625c86143298b23d"
CORE_TREE = "76d0cff342da3d47cfd8250feea0e9ea37cd8823"
CORE_SNAPSHOT = "https://github.com/PearlLeeStudio/TheArtist f043e538facd7a2f133a35f577904ac34eff1dc6"
EXCLUDE = ("AGENTS.md", "CLAUDE.md")
# These additions extract pre-event implementation rather than introducing a
# standalone new asset. Keep their refactoring in the patch, with attribution.
PATCH_ONLY_ADDITIONS = {
    "frontend/src/components/ScoreEditor/scoreSurface.ts",
    "frontend/src/engine/drumPatterns.ts",
    "frontend/src/engine/genres.ts",
    "frontend/src/engine/manualChordDraft.ts",
}


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def blocks(content):
    try:
        lines = [line.strip() for line in content.decode().splitlines() if line.strip()]
    except UnicodeDecodeError:
        return set()
    return {"\n".join(lines[i:i + 3]) for i in range(len(lines) - 2)
            if sum(map(len, lines[i:i + 3])) >= 80}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.out.is_absolute() or args.out.exists():
        parser.error("Use a new absolute output directory")
    if git("status", "--porcelain").strip():
        parser.error("Commit the development working tree before extraction")
    if git("rev-parse", "baseline^{tree}").decode().strip() != CORE_TREE:
        raise SystemExit("Baseline no longer matches the pinned public core")
    if git("rev-parse", "baseline^{commit}").decode().strip() != CORE_COMMIT:
        raise SystemExit("The baseline tag no longer points at the pinned core commit")
    head = git("rev-parse", "HEAD").decode().strip()
    paths = [".", *(f":(exclude){name}" for name in EXCLUDE)]
    changed = git("diff", "--name-only", "--no-renames", "-z", "baseline", head, "--", *paths).split(b"\0")
    base = {name.decode(): git("show", f"baseline:{name.decode()}") for name in
            git("ls-tree", "-r", "--name-only", "-z", "baseline").split(b"\0") if name}
    base_blocks = {name: blocks(content) for name, content in base.items()}
    manifest_files, materialized, added, patch_paths = {}, {}, [], []
    args.out.mkdir(parents=True)
    for raw in changed:
        if not raw:
            continue
        name = raw.decode()
        file = ROOT / name
        if not file.exists():
            manifest_files[name] = None
            patch_paths.append(name)
            continue
        content = git("show", f"{head}:{name}")
        manifest_files[name] = hashlib.sha256(content).hexdigest()
        # New source/docs/results are inspectable without applying a patch.
        # Updated screenshots are event-created assets, even at an older path.
        if (name not in base and name not in PATCH_ONLY_ADDITIONS) or name.startswith("screenshot/"):
            mode = git("ls-tree", head, "--", name).decode().split()[0]
            if mode not in {"100644", "100755"}:
                raise SystemExit(f"Unsupported contribution file mode: {name}")
            materialized[name] = dict(mode=mode, replacesCore=name in base)
            target = args.out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o755 if mode == "100755" else 0o644)
        else:
            patch_paths.append(name)
        if name in base:
            continue
        spans = blocks(content)
        matches = []
        for old_name, old_content in base.items():
            shared = len(spans & base_blocks[old_name])
            if content == old_content or (shared >= 3 and shared / max(1, len(spans)) >= .15):
                matches.append(dict(path=old_name, exact=content == old_content,
                                    sharedBlocks=shared, addedFileBlocks=len(spans)))
        added.append(dict(path=name, delivery="file" if name in materialized else "patch",
                          candidates=sorted(matches, key=lambda x: -x["sharedBlocks"])[:5]))
    patch = git("diff", "--binary", "--full-index", "--no-renames", "baseline", head,
                "--", *patch_paths) if patch_paths else b""
    (args.out / "changes.patch").write_bytes(patch)
    manifest = dict(version=2, core=dict(repository=CORE_REPOSITORY, ref="baseline",
                    commit=CORE_COMMIT, tree=CORE_TREE, snapshotOf=CORE_SNAPSHOT),
                    development=dict(repository="https://github.com/PearlLeeStudio/TheArtist-DAW", commit=head),
                    patchSha256=hashlib.sha256(patch).hexdigest(),
                    materializedFiles=materialized, files=manifest_files)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (args.out / "provenance-review.json").write_text(json.dumps(dict(
        method="Exact bytes and normalized three-line blocks; manual review remains required. "
               "A git-added file can contain pre-event code. Extracted implementation stays in the patch; "
               "derived documentation, empty package markers and generated lock metadata are disclosed in README.",
        addedFiles=added), indent=2) + "\n")
    shutil.copyfile(ROOT / "scripts/bootstrap_submission.py", args.out / "bootstrap.py")
    shutil.copyfile(ROOT / "scripts/submission_README.md", args.out / "README.md")
    shutil.copyfile(ROOT / "LICENSE", args.out / "LICENSE")
    print(f"Extracted {len(materialized)} browsable files and {len(patch_paths)} patched paths "
          f"({len(manifest_files)} total) at {head}; "
          f"{sum(bool(row['candidates']) for row in added)} added paths need provenance review")


if __name__ == "__main__":
    main()
