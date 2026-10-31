"""Reproducible JAZZVAR inputs; no model/API use or silent quality simplification.

Original harmony must match a supported pitch-class set exactly, using only
explicitly separated accompaniment tracks. Performance MIDI is a note-profile
reference, never an expert chord-label ground truth. Downloaded data stays local.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

import mido

SOURCE = 'https://zenodo.org/records/11264676'
LICENSE = 'CC BY-NC-SA 2.0'
EXPECTED_MD5 = '7084a3c7bca5126880f9c24aac41fd3a'


def midi_tracks(data, *, require_four_four=True):
    midi = mido.MidiFile(file=io.BytesIO(data))
    tracks, meters = [], set()
    for track in midi.tracks:
        now, name, active, notes = 0, '', defaultdict(list), []
        for event in track:
            now += event.time
            if event.type == 'track_name':
                name = event.name
            if event.type == 'time_signature':
                meters.add((event.numerator, event.denominator))
            if event.type == 'note_on' and event.velocity:
                active[(event.channel, event.note)].append(now)
            elif event.type == 'note_off' or (event.type == 'note_on' and not event.velocity):
                pending = active[(event.channel, event.note)]
                if pending:
                    start = pending.pop(0)
                    if now > start:
                        notes.append((start / midi.ticks_per_beat, now / midi.ticks_per_beat, event.note))
        if any(active.values()):
            raise ValueError('Unclosed MIDI notes')
        if notes:
            tracks.append({'name': name, 'notes': sorted(notes)})
    if require_four_four and meters and meters != {(4, 4)}:
        raise ValueError('Explicit MIDI meter is not constant 4/4')
    return tracks


def profile(notes, start, end, transpose=0):
    weights = [0.0] * 12
    for onset, offset, note in notes:
        duration = max(0, min(offset, end) - max(onset, start))
        weights[(note + transpose) % 12] += duration
    total = sum(weights)
    return [round(w / total, 8) if total else 0 for w in weights]


def exact_symbol(notes, position):
    from app.services.reharmonize import INTERVALS, ROOTS
    sounding = sorted(n for onset, offset, n in notes if onset <= position < offset)
    if not sounding:
        raise ValueError('Missing accompaniment at a half-bar anchor')
    pcs, bass = frozenset(n % 12 for n in sounding), sounding[0] % 12
    matches = []
    for root, name in enumerate(ROOTS):
        for quality, intervals in INTERVALS.items():
            if {(root + interval) % 12 for interval in intervals} == pcs:
                symbol = name + ('' if quality == 'maj' else quality)
                if root != bass:
                    symbol += '/' + ROOTS[bass]
                matches.append((root != bass, len(quality), symbol))
    if not matches:
        raise ValueError('Accompaniment pitch classes require an unsupported chord quality')
    matches.sort()
    # Root-position matches resolve e.g. C6/Am7 ambiguities through the actual bass.
    best = matches[0]
    if best[0] and len(matches) > 1:
        raise ValueError('Ambiguous root in an inverted accompaniment')
    return best[2]


def key_parts(value):
    from app.services.reharmonize import pitch
    tonic, mode = value.split()
    if mode.lower() not in ('major', 'minor'):
        raise ValueError('Unsupported source key')
    return pitch(tonic), mode.lower()


def monophonic(notes):
    return all(a[1] <= b[0] + .02 for a, b in zip(sorted(notes), sorted(notes)[1:]))


def tune_group(title):
    # Recording suffixes and capitalization are not independent compositions.
    return re.sub(r'[^a-z0-9]', '', title.split(' - ')[0].casefold())


def prepare_pair(archive, row):
    from app.services.reharmonize import ROOTS, chord
    xname = 'JAZZVAR_DATASET/x_labels/' + row['x_label']
    yname = 'JAZZVAR_DATASET/y_labels/' + row['y_label']
    xdata, ydata = archive.read(xname), archive.read(yname)
    original, variation = midi_tracks(xdata), midi_tracks(ydata, require_four_four=False)
    melody = [t for t in original if 'melody' in t['name'].lower()]
    separation = 'Explicit melody track'
    if not melody:
        # Some lead sheets call their melody MusicXML Part. Accept only a
        # separate monophonic track higher on average than every other track.
        ranked = sorted(original, key=lambda t: sum(n[2] for n in t['notes']) / len(t['notes']), reverse=True)
        if len(ranked) >= 2 and monophonic(ranked[0]['notes']):
            melody = [ranked[0]]
            separation = 'Highest separate monophonic track'
    accompaniment = [t for t in original if not any(t is m for m in melody)]
    if len(melody) != 1 or not accompaniment:
        raise ValueError('Original has no unambiguous separate melody track')
    harmony = [n for t in accompaniment for n in t['notes']]
    performance = [n for t in variation for n in t['notes']]
    if not performance:
        raise ValueError('Empty variation MIDI')
    if not 14 <= max(n[1] for t in original for n in t['notes']) <= 17:
        raise ValueError('Original does not span approximately four 4/4 bars')
    xroot, xmode = key_parts(row['x_label_key'])
    yroot, ymode = key_parts(row['y_label_key'])
    if xmode != ymode:
        raise ValueError('Original and performance have different annotated modes')
    symbols = [exact_symbol(harmony, i * 2 + .125) for i in range(8)]
    for symbol in symbols:
        chord(symbol)
    return {
        'id': 'jazzvar-' + row['x_label'].removesuffix('.mid'),
        'tune': row['track'].split(' - ')[0], 'tuneGroup': tune_group(row['track']), 'performer': row['track_artists'],
        'melodySeparation': separation,
        'source': SOURCE, 'license': LICENSE,
        'originalFile': row['x_label'], 'variationFile': row['y_label'],
        'originalSha256': hashlib.sha256(xdata).hexdigest(),
        'variationSha256': hashlib.sha256(ydata).hexdigest(),
        'originalKey': row['x_label_key'], 'variationKey': row['y_label_key'],
        'request': {'key': ROOTS[xroot] + ' ' + xmode, 'timeSignature': [4, 4],
                    'context': [{'measure': i, 'chords': symbols[2*i:2*i+2]} for i in range(4)],
                    'selectedSlots': [{'measureIndex': 1, 'slotIndex': 0}, {'measureIndex': 1, 'slotIndex': 1}],
                    'maxChanges': 2, 'mode': 'auto', 'modelKey': 'ft_f4'},
        'melodyProfiles': [profile(melody[0]['notes'], i * 2, i * 2 + 2) for i in range(8)],
        # Performance timing/meters are inconsistent across MIDI exports. Use
        # only a whole-excerpt profile; do not fabricate beat alignment or chords.
        'variationProfile': profile(performance, 0, max(n[1] for n in performance), xroot - yroot),
        'variationTiming': 'Whole-excerpt pitch-class profile; no beat alignment claimed',
    }


def build_dataset(zip_path: Path, maximum=48):
    payload = zip_path.read_bytes()
    if hashlib.md5(payload).hexdigest() != EXPECTED_MD5:
        raise ValueError('JAZZVAR archive checksum mismatch')
    archive = ZipFile(io.BytesIO(payload))
    rows = list(csv.DictReader(io.StringIO(archive.read('JAZZVAR_DATASET/metadata.csv').decode())))
    excluded, eligible, seen_ids, signatures = [], [], set(), set()
    for row in sorted(rows, key=lambda r: r['x_label']):
        if row['x_label'] in seen_ids:
            excluded.append({'id': row['x_label'], 'reason': 'Duplicate metadata identifier'})
            continue
        seen_ids.add(row['x_label'])
        try:
            case = prepare_pair(archive, row)
            signature = (case['tuneGroup'], json.dumps(case['request']['context'], sort_keys=True),
                         json.dumps(case['melodyProfiles']))
            if signature in signatures:
                raise ValueError('Duplicate original harmony within the same tune')
            signatures.add(signature)
            eligible.append(case)
        except (ValueError, KeyError, EOFError) as exc:
            excluded.append({'id': row['x_label'], 'reason': str(exc)})
    # Round-robin by tune; at most three windows per tune. Freeze before any API call.
    groups = defaultdict(list)
    for case in eligible:
        groups[case['tuneGroup']].append(case)
    for cases in groups.values():
        cases.sort(key=lambda c: hashlib.sha256(c['id'].encode()).hexdigest())
    selected = []
    for i in range(3):
        for title in sorted(groups):
            if i < len(groups[title]) and len(selected) < maximum:
                selected.append(groups[title][i])
    return {'source': SOURCE, 'license': LICENSE, 'archiveMd5': EXPECTED_MD5,
            'metadataRows': len(rows), 'eligible': len(eligible), 'eligibleTunes': len(groups),
            'exclusions': excluded, 'exclusionCounts': dict(Counter(e['reason'] for e in excluded)),
            'selection': 'Fixed hash order; tune-balanced round robin; at most three windows per tune; no result-based selection.',
            'cases': selected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--maximum', type=int, default=48)
    args = parser.parse_args()
    if not all(path.is_absolute() for path in (args.backend, args.archive, args.output)):
        parser.error('Use absolute paths')
    if args.output.exists():
        parser.error('Preserve the frozen dataset; use a new output path')
    if args.maximum < 1:
        parser.error('maximum must be positive')
    sys.path.insert(0, str(args.backend))
    dataset = build_dataset(args.archive, args.maximum)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2))
    print(json.dumps({key: dataset[key] for key in ('metadataRows', 'eligible', 'eligibleTunes', 'exclusionCounts')}))
    print(f"Selected {len(dataset['cases'])} paired passages")


if __name__ == '__main__':
    main()
