"""Extract event changes as a patch against a separately acquired, pinned core.

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
CORE_COMMIT = "f043e538facd7a2f133a35f577904ac34eff1dc6"
CORE_TREE = "76d0cff342da3d47cfd8250feea0e9ea37cd8823"
EXCLUDE = ("AGENTS.md", "CLAUDE.md")


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
    head = git("rev-parse", "HEAD").decode().strip()
    paths = [".", *(f":(exclude){name}" for name in EXCLUDE)]
    patch = git("diff", "--binary", "--full-index", "--no-renames", "baseline", head, "--", *paths)
    changed = git("diff", "--name-only", "--no-renames", "-z", "baseline", head, "--", *paths).split(b"\0")
    base = {name.decode(): git("show", f"baseline:{name.decode()}") for name in
            git("ls-tree", "-r", "--name-only", "-z", "baseline").split(b"\0") if name}
    base_blocks = {name: blocks(content) for name, content in base.items()}
    manifest_files, added = {}, []
    for raw in changed:
        if not raw:
            continue
        name = raw.decode()
        file = ROOT / name
        if not file.exists():
            manifest_files[name] = None
            continue
        content = file.read_bytes()
        manifest_files[name] = hashlib.sha256(content).hexdigest()
        if name in base:
            continue
        spans = blocks(content)
        matches = []
        for old_name, old_content in base.items():
            shared = len(spans & base_blocks[old_name])
            if content == old_content or (shared >= 3 and shared / max(1, len(spans)) >= .15):
                matches.append(dict(path=old_name, exact=content == old_content,
                                    sharedBlocks=shared, addedFileBlocks=len(spans)))
        added.append(dict(path=name, candidates=sorted(matches, key=lambda x: -x["sharedBlocks"])[:5]))
    args.out.mkdir(parents=True)
    (args.out / "changes.patch").write_bytes(patch)
    manifest = dict(version=1, core=dict(repository="https://github.com/PearlLeeStudio/TheArtist.git",
                    commit=CORE_COMMIT, tree=CORE_TREE),
                    development=dict(repository="https://github.com/PearlLeeStudio/TheArtist-DAW", commit=head),
                    patchSha256=hashlib.sha256(patch).hexdigest(), files=manifest_files)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (args.out / "provenance-review.json").write_text(json.dumps(dict(
        method="Exact bytes and normalized three-line blocks; manual review remains required. "
               "A git-added file can contain pre-event code. All such files remain patch deltas, not claimed new assets.",
        addedFiles=added), indent=2) + "\n")
    shutil.copyfile(ROOT / "scripts/bootstrap_submission.py", args.out / "bootstrap.py")
    shutil.copyfile(ROOT / "scripts/submission_README.md", args.out / "README.md")
    shutil.copyfile(ROOT / "LICENSE", args.out / "LICENSE")
    print(f"Extracted {len(manifest_files)} changed paths at {head}; "
          f"{sum(bool(row['candidates']) for row in added)} added paths need provenance review")


if __name__ == "__main__":
    main()
