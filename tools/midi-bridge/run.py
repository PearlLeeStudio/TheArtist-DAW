"""Build and run the Mac MIDI bridge, using only Python's standard library and Swift."""
import os
from pathlib import Path
import platform
import subprocess
import sys


def main():
    if platform.system() != "Darwin":
        raise SystemExit("The local bridge currently supports macOS. Chrome Web MIDI works without it.")
    source = Path(__file__).resolve().parent
    build = source / ".build"
    build.mkdir(exist_ok=True)
    cache = build / "ModuleCache"
    cache.mkdir(exist_ok=True)
    helper = build / "CoreMidiInput"
    swift = source / "CoreMidiInput.swift"
    if not helper.exists() or helper.stat().st_mtime < swift.stat().st_mtime:
        subprocess.run(["/usr/bin/swiftc", "-module-cache-path", str(cache), str(swift), "-o", str(helper)], check=True)
    os.execv(sys.executable, [sys.executable, str(source / "bridge.py"), "--helper", str(helper)])


if __name__ == "__main__":
    main()
