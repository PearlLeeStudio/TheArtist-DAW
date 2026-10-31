"""CPU F1 continuation against fixed DCML Mozart annotations, not a listening test.

Four bars of context, then four bars to predict, sampled at two slots per bar.
The first returned candidate is the preselected primary result; no oracle choice.
"""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from statistics import mean
import sys

NAMES = ('C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B')
QUALITY = {'M': '', 'm': 'm', 'o': 'dim', '+': 'aug', 'Mm7': '7',
           'MM7': 'maj7', 'mm7': 'm7', 'o7': 'dim7', '%7': 'm7b5'}


def convert(row):
    from music21 import key, roman
    global_key = key.Key(row['globalkey'][0] + row['globalkey'][1:].replace('b', '-'))
    tonic = roman.RomanNumeral(row['localkey'], global_key).root().pitchClass
    root = (tonic + 7 * int(row['root'])) % 12
    pcs = sorted({(tonic + 7 * int(n.strip())) % 12 for n in row['chord_tones'].split(',')})
    if row['chord_type'] not in QUALITY:
        raise ValueError('Unsupported reference chord type: ' + row['chord_type'])
    bass = (tonic + 7 * int(row['bass_note'])) % 12
    symbol = NAMES[root] + QUALITY[row['chord_type']]
    if bass != root:
        symbol += '/' + NAMES[bass]
    return {'symbol': symbol, 'root': root, 'pcs': pcs}


def prepare(path):
    rows = list(csv.DictReader(path.open(), delimiter='\t'))
    first = rows[0]
    meter = tuple(map(int, first['timesig'].split('/')))
    bar_duration = Fraction(4 * meter[0], meter[1])
    annotated = [r for r in rows if r['quarterbeats'] and r['root'] and r['chord_tones']]
    horizon = 8 * bar_duration
    if any(r['timesig'] != first['timesig'] for r in annotated if Fraction(r['quarterbeats']) < horizon):
        raise ValueError('Meter changes within the fixed excerpt')
    slots = []
    for i in range(16):
        position = i * bar_duration / 2
        matches = [r for r in annotated if Fraction(r['quarterbeats']) <= position <
                   Fraction(r['quarterbeats']) + Fraction(r['duration_qb'])]
        if len(matches) != 1:
            raise ValueError(f'Expected one reference harmony at slot {i}; found {len(matches)}')
        slots.append(convert(matches[0]))
    tonic = first['globalkey'][0].upper() + first['globalkey'][1:]
    mode = 'minor' if first['globalkey_is_minor'] == '1' else 'major'
    return {'id': path.name.split('.')[0], 'key': tonic + ' ' + mode, 'meter': meter,
            'sourceSha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'context': [s['symbol'] for s in slots[:8]], 'reference': slots[8:]}


def describe(symbol):
    from music21 import harmony
    symbol = symbol.replace('♭', 'b').replace('♯', '#')
    symbol = re.sub(r'(^|/)([A-G])b', r'\1\2-', symbol)
    symbol = symbol.replace('mMaj', 'mM').replace('maj9', 'M9')
    chord = harmony.ChordSymbol(symbol)
    return {'pcs': sorted({p.pitchClass for p in chord.pitches}), 'root': chord.root().pitchClass}


def score(symbols, reference):
    values = []
    for index, expected in enumerate(reference):
        try:
            actual = describe(symbols[index])
            a, b = set(actual['pcs']), set(expected['pcs'])
            values.append({'valid': 1, 'pitchJaccard': len(a & b) / len(a | b),
                           'pitchSetExact': int(a == b), 'rootExact': int(actual['root'] == expected['root'])})
        except (ValueError, IndexError, TypeError) as exc:
            values.append({'valid': 0, 'pitchJaccard': 0, 'pitchSetExact': 0, 'rootExact': 0,
                           'errorType': type(exc).__name__})
    return {field: mean(v[field] for v in values) for field in ('valid', 'pitchJaccard', 'pitchSetExact', 'rootExact')}


def summarize(report):
    metrics = ('valid', 'pitchJaccard', 'pitchSetExact', 'rootExact')
    return {
        'candidateA': {m: mean(r['candidates'][0]['metrics'][m] for c in report['cases'] for r in c['runs']) for m in metrics},
        'allCandidates': {m: mean(s['metrics'][m] for c in report['cases'] for r in c['runs'] for s in r['candidates']) for m in metrics},
        **{b: {m: mean(c['baselines'][b][m] for c in report['cases']) for m in metrics} for b in ('holdLast', 'tonic')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('backend', 'sources', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--rescore', type=Path, help='Recompute metrics for saved predictions without generation')
    args = parser.parse_args()
    if any(not p.is_absolute() for p in (args.backend, args.sources, args.output)) or args.output.exists():
        parser.error('Use absolute paths and a new output')
    sys.path.insert(0, str(args.backend))
    from app.models.schemas import ContextMeasure, SectionGenerateRequest
    from app.routes.generate import compose_section
    from app.services.inference import ModelRegistry
    from app.services.contracts import capabilities
    import torch

    # Independently specified conversion anchors from the corpus convention.
    anchor = dict(globalkey='C', localkey='I', root='2', bass_note='-1', chord_tones='-1, 3, 2', chord_type='m')
    assert convert(anchor) == {'symbol': 'Dm/F', 'root': 2, 'pcs': [2, 5, 9]}
    assert describe('Dm/F')['pcs'] == [2, 5, 9]
    assert describe('Bbmaj/D')['pcs'] == [2, 5, 10]
    assert describe('AmMaj7/E')['pcs'] == [0, 4, 8, 9]
    assert describe('Dmaj9')['pcs'] == [1, 2, 4, 6, 9]
    assert score(['C'], [{'root': 0, 'pcs': [0, 4, 7]}])['pitchSetExact'] == 1
    assert score(['C'], [{'root': 2, 'pcs': [2, 5, 9]}])['pitchJaccard'] == 0
    if args.rescore:
        if not args.rescore.is_absolute():
            parser.error('Use an absolute saved result path')
        report = json.loads(args.rescore.read_text())
        for case in report['cases']:
            tonic = case['key'].split()[0] + ('m' if case['key'].endswith('minor') else '')
            case['baselines'] = {'holdLast': score([case['context'][-1]] * 8, case['reference']),
                                 'tonic': score([tonic] * 8, case['reference'])}
            for run in case['runs']:
                for candidate in run['candidates']:
                    candidate['metrics'] = score(candidate['chords'], case['reference'])
        report['summary'] = summarize(report)
        report['metricNotation'] = 'Normalize flat roots/slash bass and mMaj7/maj9 into music21 notation; saved predictions unchanged.'
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report['summary']), flush=True)
        return
    manifest = json.loads((args.sources / 'sources.json').read_text())['dcml']
    cases, excluded = [], []
    for item in manifest['files']:
        path = args.sources / item['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Source digest mismatch')
        try:
            cases.append(prepare(path))
        except ValueError as exc:
            excluded.append({'id': item['id'], 'reason': str(exc)})
    if not cases:
        raise ValueError('No eligible excerpts')
    torch.set_num_threads(4)
    loaded = ModelRegistry.get().load_model('ft_f1')
    if loaded is None or str(loaded.device) != 'cpu':
        raise ValueError('The actual F1 CPU model is required')
    rag = capabilities().data['rag']['sources']
    if rag != {'omt': 'ready', 'berklee': 'disabled'}:
        raise ValueError('Use the product OMT configuration with Berklee disabled')
    report = {'method': 'First eight written bars, sampled twice per bar: four context bars plus four target bars. Candidate A is primary. All three candidates retained. No reference-based reranking; no training.',
              'limitations': ['Reference continuation agreement is not music quality or listener preference.',
                              'One composer, short excerpts, unknown overlap with pretraining.',
                              'Sampling at two slots discards between-slot changes and durations.',
                              'Context chord types are simplified; reference pitch-class sets retain annotated chord tones.',
                              'Product F1 generation includes existing R1 and voice-leading postprocessing; not a raw neural-model benchmark.'],
              'corpus': {k: v for k, v in manifest.items() if k != 'files'},
              'device': str(loaded.device), 'threads': 4, 'rag': rag, 'seeds': [17, 18, 19],
              'excluded': excluded, 'cases': []}
    for case in cases:
        ctx = case['context']
        tonic = case['key'].split()[0] + ('m' if case['key'].endswith('minor') else '')
        record = {**case, 'baselines': {'holdLast': score([ctx[-1]] * 8, case['reference']),
                                     'tonic': score([tonic] * 8, case['reference'])}, 'runs': []}
        for seed in report['seeds']:
            request = SectionGenerateRequest(key=case['key'], genre='classical', timeSignature=case['meter'],
                                             sectionType='a_section', chordCount=8, modelKey='ft_f1', seed=seed,
                                             cadence='none', context=[ContextMeasure(measure=i, chords=ctx[2*i:2*i+2]) for i in range(4)])
            response = compose_section(request)
            if response.source != 'ai' or response.modelUsed != 'ft_f1':
                raise ValueError('Rules fallback is not an F1 result')
            candidates = []
            for suggestion in response.suggestions:
                symbols = [c for i in range(4, 8) for c in suggestion.chords[str(i)]]
                if len(symbols) != 8:
                    raise ValueError('Unexpected output length')
                candidates.append({'label': suggestion.label, 'chords': symbols, 'metrics': score(symbols, case['reference'])})
            record['runs'].append({'seed': seed, 'source': response.source, 'model': response.modelUsed,
                                   'candidates': candidates})
        report['cases'].append(record)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(f"{case['id']}: 3 seeds / {sum(len(r['candidates']) for r in record['runs'])} candidates, source=ai", flush=True)
    report['summary'] = summarize(report)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
