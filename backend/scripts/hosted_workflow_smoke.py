"""Hosted catalog and Meta workflow smoke; paid calls require --meta.

Exercises public synthetic inputs only and saves metadata, not source scores.
This checks execution/provenance, not musical quality or comparative latency.
"""
import argparse
import base64
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--meta', action='store_true')
    args = parser.parse_args()
    if not args.out.is_absolute():
        parser.error('--out must be absolute')
    session = 'workflow-probe-' + uuid.uuid4().hex
    rows = []

    def call(route, payload=None):
        request = Request(args.url.rstrip('/') + route,
                          data=json.dumps(payload).encode() if payload is not None else None,
                          headers={'Content-Type': 'application/json', 'X-TheArtist-Session': session})
        started = time.perf_counter()
        with urlopen(request, timeout=200) as response:
            data = json.load(response)
        return data, round(time.perf_counter() - started, 3)

    def record(row):
        rows.append(row)
        args.out.write_text(json.dumps(rows, indent=2) + '\n')
        print(json.dumps(row), flush=True)

    catalog, _ = call('/api/models/list')
    assert len(catalog['models']) == 18 and all(m['available'] for m in catalog['models'])
    for model in catalog['models']:
        key = model['key']
        genre = key.removeprefix('ft_f1_lora_') if key.startswith('ft_f1_lora_') else 'pop'
        data, seconds = call('/api/generate/section', dict(
            key='C major', genre=genre, sectionType='verse', chordCount=16, modelKey=key, seed=17))
        assert data['source'] == 'ai' and data['modelUsed'] == key, data
        assert len(data['suggestions']) == 3 and all(len(s['chords']) == 8 for s in data['suggestions'])
        record(dict(case=key, seconds=seconds, candidates=3, bars=8))
    if not args.meta:
        return
    for source in ('own', 'meta'):
        data, seconds = call('/api/plan/song', dict(
            genre='pop', key='C major', targetBars=32, planner='meta', chordSource=source,
            modelKey='ft_f1', seed=17))
        assert data['status'] == 'ok' and sum(s['bars'] for s in data['sections']) == 32, data
        record(dict(case='song_form_' + source, seconds=seconds, calls=data['calls'],
                    meta_ms=data['metaMs'], generation_ms=data['generationMs'], cost_usd=data['spendUsd']))
    data, seconds = call('/api/review/candidates', dict(
        key='C major', genre='pop', sectionType='verse', original=[['C', 'Am'], ['Dm', 'G7']],
        candidates=[dict(label='A', chords=[['Cmaj7', 'Am7'], ['Dm7', 'G7']]),
                    dict(label='B', chords=[['C', 'F'], ['Dm', 'G7']])]))
    assert data['choice'] in ('A', 'B') and data['requestId'], data
    record(dict(case='second_ear', seconds=seconds, request_id=data['requestId'], cost_usd=data['costUsd']))
    # The repository's authored one-bar fixture; never a user's uploaded score.
    fixture = Path(__file__).resolve().parents[1] / 'tests/fixtures/vector-score-c.pdf'
    data, seconds = call('/api/import/score', dict(
        filename='vector-score-c.pdf', mimeType='application/pdf', engine='verified', mode='infer_harmony',
        dataBase64=base64.b64encode(fixture.read_bytes()).decode()))
    assert data['measures'] and data['verification'], data
    record(dict(case='verified_import', seconds=seconds, measures=len(data['measures']),
                verification=data['verification']['status'], request_id=data['requestId']))


if __name__ == '__main__':
    main()
