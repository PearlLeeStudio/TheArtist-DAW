"""Create a portable, label-concealed listening page and a separate answer key.

No model/API calls. The page randomizes A/B independently, renders harmony/bass
with the same simple Web Audio voices, and exports unfilled human responses.
The answer key is written only to the explicitly supplied private path.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

import mido

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))


def notes(midi_bytes):
    active, events, levels = {}, [], {}
    clock = 0.0
    for message in mido.MidiFile(file=io.BytesIO(midi_bytes)):
        clock += message.time
        if message.is_meta or message.channel == 9:
            continue
        channel = message.channel
        if message.type == "control_change" and message.control == 7:
            levels[channel] = message.value / 127
        if message.type not in {"note_on", "note_off"}:
            continue
        key = (channel, message.note)
        if message.type == "note_on" and message.velocity:
            active.setdefault(key, []).append((clock, message.velocity / 127 * levels.get(channel, 1)))
        elif active.get(key):
            start, velocity = active[key].pop(0)
            events.append([round(start, 5), round(clock - start, 5), message.note, round(velocity, 4), channel])
    if any(active.values()):
        raise ValueError("MIDI has unmatched notes; refuse an incomplete listening render")
    if not events:
        raise ValueError("No harmony/bass notes to compare")
    return sorted(events), round(clock, 5)


def package(pairs, html_path, key_path):
    if not html_path.is_absolute() or not key_path.is_absolute() or html_path.exists() or key_path.exists():
        raise ValueError("Use new absolute output and private answer-key paths")
    public, answer_key = [], {}
    for pair_id, label, arms in pairs:
        variants = []
        for arm, midi_bytes in arms.items():
            identifier = hashlib.sha256(midi_bytes).hexdigest()
            events, duration = notes(midi_bytes)
            variants.append(dict(id=identifier, events=events, duration=duration))
            answer_key[identifier] = dict(pair=pair_id, arm=arm)
        if len(variants) != 2:
            raise ValueError("Each comparison needs exactly two arms")
        public.append(dict(id=pair_id, label=label, variants=variants))
    template = (ROOT / "agent/listening_template.html").read_text()
    # Keep model names, file names, dates and the arm key out of the distributed page.
    html_path.write_text(template.replace("__LISTENING_DATA__", json.dumps(public).replace("<", "\\u003c")))
    key_path.write_text(json.dumps(answer_key, indent=2) + "\n")
    print(f"Created {len(public)} comparisons; no human ratings have been collected.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--midi-dir", type=Path)
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.midi_dir) == bool(args.benchmark):
        parser.error("Choose either --midi-dir or --benchmark")
    pairs = []
    if args.midi_dir:
        for i, (name, label) in enumerate((("new_pop_32", "Pop"), ("new_jazz_32", "Jazz"),
                                          ("complete_hiphop_amin_8bar_32", "Minor-key hip-hop"))):
            pairs.append((f"pair-{i + 1}", label, {arm: (args.midi_dir / f"{name}-{arm}.mid").read_bytes()
                                                   for arm in ("rules", "meta")}))
    else:
        from agent.export_plan_samples import snapshot
        from app.services.smf_export import render_midi
        document = json.loads(args.benchmark.read_text())
        for i, case in enumerate(document["cases"]):
            pairs.append((f"pair-{i + 1}", case["name"], {
                mode: render_midi(snapshot(case["listening"][mode], mode)) for mode in ("new", "reuse")
            }))
    package(pairs, args.out, args.private_key)


if __name__ == "__main__":
    main()
