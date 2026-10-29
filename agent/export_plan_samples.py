"""Render three predetermined paired traces to MIDI for later listening, with no API call.

Uses canonical octave-4 chord voicings and the product's MIDI arrangement renderer.
This is a listening artifact, not a listening evaluation or editor-voicing capture.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import mido

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend"))

from ai.physics.voicing import voice_chord  # noqa: E402
from app.models.export import ExportSpec  # noqa: E402
from app.services.smf_export import render_midi  # noqa: E402

SAMPLES = ("new_pop_32", "new_jazz_32", "complete_hiphop_amin_8bar_32")
PLAY = {"harmonyOverride": "acoustic_grand_piano", "harmonyRhythmId": None, "bassEnabled": True,
        "drumMode": "auto", "drumPatternId": None, "masterVolume": 0.8,
        "harmonyVolume": 0.8, "bassVolume": 0.65, "drumVolume": 0.55}


def snapshot(run: dict, arm: str) -> ExportSpec:
    request, trace = run["requestBody"], run["trace"]
    if trace["status"] != "ok":
        raise ValueError("Cannot export an incomplete evaluated song")
    slots = [bar["chords"] for bar in request["measures"]]
    sections = [{"label": section["type"], "startMeasure": section["start"], "length": section["length"]}
                for section in request["sections"]]
    for section in trace["sections"]:
        if section["startMeasure"] != len(slots):
            raise ValueError("Generated sections must continue the exact saved sketch")
        chords = section["suggestions"][0]["chords"]
        indices = sorted(map(int, chords))
        if indices != list(range(len(slots), len(slots) + section["bars"])):
            raise ValueError("Generated chord measures are not contiguous")
        sections.append({"label": section["sectionType"], "startMeasure": len(slots), "length": section["bars"]})
        slots.extend(chords[str(index)] for index in indices)
    if len(slots) != request["targetBars"]:
        raise ValueError("Song length differs from the saved request")
    measures = []
    for bar in slots:
        voiced = []
        for symbol in bar:
            notes = voice_chord(symbol) if symbol else None
            if symbol and not notes:
                raise ValueError(f"Could not voice saved chord {symbol!r}; no silent substitution")
            voiced.append({"symbol": symbol, "voicing": notes} if symbol else None)
        measures.append({"chords": voiced})
    return ExportSpec.model_validate({"title": f"{run['request']} — {arm}", "key": request["key"],
                                      "bpm": request["bpm"], "timeSignature": request["timeSignature"],
                                      "genre": request["genre"], "measures": measures,
                                      "sections": sections, "play": PLAY})


def export(results: Path, out: Path) -> None:
    if out.exists():
        raise ValueError("Output folder exists; preserve prior listening artifacts")
    rendered = []
    seed = None
    controls = None
    paired_inputs = {}
    for arm, filename in (("rules", "rules.json"), ("meta", "meta-medium.json")):
        document = json.loads((results / filename).read_text(encoding="utf-8"))
        if document["planner"] != arm:
            raise ValueError("Listening result document has the wrong planner")
        if seed is not None and seed != document["samplingSeed"]:
            raise ValueError("Both listening arms must use the same base seed")
        seed = document["samplingSeed"]
        current_controls = (document["chordModel"], document["controls"])
        if controls is not None and controls != current_controls:
            raise ValueError("Both listening arms must use the same model and generation controls")
        controls = current_controls
        runs = {run["request"]: run for run in document["runs"]}
        for name in SAMPLES:
            run = runs[name]
            body = run["requestBody"]
            if run["samplingSeed"] != body["seed"] or body["modelKey"] != document["chordModel"]:
                raise ValueError("Listening run differs from its recorded seed/model controls")
            comparable = {key: value for key, value in body.items() if key != "planner"}
            if name in paired_inputs and paired_inputs[name] != comparable:
                raise ValueError("Both listening arms must use the exact same saved request and sampling seed")
            paired_inputs[name] = comparable
            spec = snapshot(run, arm)
            midi = render_midi(spec)
            decoded = mido.MidiFile(file=io.BytesIO(midi))
            expected_ticks = round(len(spec.measures) * spec.timeSignature[0] * 4 / spec.timeSignature[1]
                                   * decoded.ticks_per_beat)
            if not all(sum(event.time for event in track) == expected_ticks for track in decoded.tracks):
                raise ValueError("Rendered MIDI duration does not match the saved song")
            rendered.append((f"{name}-{arm}.mid", midi, len(spec.measures)))
    out.mkdir(parents=True)
    for name, midi, bars in rendered:
        (out / name).write_bytes(midi)
        print(f"{name}: {bars} bars, {len(midi)} bytes")
    (out / "README.md").write_text(
        "# Paired listening samples\n\n"
        f"Three predetermined fixtures from seed {seed}: new pop, new jazz, and A-minor hip-hop completion. "
        "Each pair uses the same sketch, tempo, genre playback settings and canonical octave-4 voicing function, "
        "then the product MIDI exporter. Final first-ranked chord suggestions are preserved, including slash bass. "
        "Canonical voicing differs from the editor's interactive voicing choices.\n\n"
        "The filenames identify the planner; these files alone are not a blind test. "
        "No audio listening was performed. No listening preference, musical quality score or superiority claim was measured. "
        "For a blind comparison, have another person hide/randomize the arm labels before rating coherence, "
        "cadence, repetition and overall preference. The minor-key completion begins with the same eight-bar "
        "sketch in both arms. No API calls or music regeneration were needed for these exports.\n",
        encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    export(args.results, args.out)


if __name__ == "__main__":
    main()
