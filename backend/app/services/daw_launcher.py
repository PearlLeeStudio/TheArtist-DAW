"""Local macOS handoff. No shell commands, uploads, or user-file replacement."""

import os
import platform
import subprocess
import uuid
from pathlib import Path

from app.models.export import MAX_EXPORT_BYTES, DawOpenResponse, DawTarget, DawTargetsResponse, ExportSpec
from app.services.smf_export import render_midi, safe_title

EXPORT_DIR = Path(__file__).resolve().parents[2] / ".exports"
_APPLICATIONS = Path("/Applications")
_LOGIC_BUNDLE = "com.apple.logic10"


class DawError(RuntimeError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def _installed(target: str) -> bool:
    if target == "logic":
        try:
            result = subprocess.run(
                ["/usr/bin/mdfind", f"kMDItemCFBundleIdentifier == '{_LOGIC_BUNDLE}'"],
                capture_output=True, text=True, timeout=3, check=False, shell=False,
            )
            if result.returncode == 0 and any(
                line.startswith("/") and line.endswith(".app") and Path(line).is_dir()
                for line in result.stdout.splitlines()
            ):
                return True
        except (OSError, subprocess.SubprocessError):
            pass  # Spotlight may be disabled; ordinary /Applications installs still work.
        pattern = "Logic Pro*.app"
    else:
        pattern = "Ableton Live*.app"
    return any(path.is_dir() for path in _APPLICATIONS.glob(pattern))


def daw_targets() -> DawTargetsResponse:
    mac = platform.system() == "Darwin"
    return DawTargetsResponse(targets=[
        DawTarget(id="logic", name="Logic Pro", available=mac and _installed("logic"), action="open"),
        DawTarget(id="ableton", name="Ableton Live", available=mac and _installed("ableton"), action="reveal"),
    ])


def _save(data: bytes, title: str) -> Path:
    if not isinstance(data, bytes) or not data.startswith(b"MThd") or not 14 <= len(data) <= MAX_EXPORT_BYTES:
        raise DawError("The MIDI could not be saved because its data is invalid.", 500)
    try:
        if EXPORT_DIR.is_symlink():
            raise OSError("export directory must not be a symlink")
        EXPORT_DIR.mkdir(mode=0o700, parents=False, exist_ok=True)
        for _ in range(5):
            path = EXPORT_DIR / f"{safe_title(title)}-{uuid.uuid4().hex[:12]}.mid"
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                continue
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            return path
        raise OSError("could not allocate a unique export filename")
    except OSError:
        raise DawError("The MIDI could not be saved to the backend export directory.", 500) from None


def _open(arguments: list[str]) -> bool:
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=10, check=False, shell=False)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def open_daw(target: str, spec: ExportSpec) -> DawOpenResponse:
    if target not in ("logic", "ableton"):
        raise DawError("Choose Logic Pro or Ableton Live.", 422)
    if platform.system() != "Darwin":
        raise DawError("Opening a DAW is available only on the local macOS backend. Download the MIDI instead.", 501)
    if not _installed(target):
        raise DawError("The selected DAW is not installed on the backend Mac. Download the MIDI instead.", 409)
    path = _save(render_midi(spec), spec.title)
    if target == "logic":
        opened = _open(["/usr/bin/open", "-b", _LOGIC_BUNDLE, str(path)])
        if not opened:
            opened = _open(["/usr/bin/open", "-a", "Logic Pro", str(path)])
        action = "open"
    else:
        opened = _open(["/usr/bin/open", "-R", str(path)])
        action = "reveal"
    if not opened:
        raise DawError(f"macOS could not {action} the MIDI. The saved file remains at {path}.", 500)
    return DawOpenResponse(action=action, path=str(path))
