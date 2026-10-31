"""Score saved four-condition runs; never call a model or change predictions."""
from __future__ import annotations

import argparse
from collections import defaultdict
import html
import json
from pathlib import Path
import random
from statistics import mean

ARMS = ('local', 'meta', 'hybrid1', 'hybrid2')
RUBRIC = ('continuity', 'melodyFit', 'usefulChange', 'retainsIdentity')


def rating_map(judge):
    if judge['status'] != 'ok':
        return {}
    return {tuple(judge['mapping'][r['id']]): {k: r[k] for k in RUBRIC}
            for r in judge['response']['data']['ratings']}


def case_facts(case):
    judges = [rating_map(j) for j in case['judges']]
    result = {'id': case['id'], 'tune': case['tune'], 'tuneGroup': case['tuneGroup'], 'arms': {}}
    for name, arm in case['arms'].items():
        facts = {'status': arm['status'], 'costUsd': arm['costUsd'], 'seconds': arm['seconds']}
        if arm['status'] == 'ok':
            candidates = arm['candidates']
            facts['valid'] = all(c['metrics']['validSparsePatch'] for c in candidates)
            facts['uniqueVersions'] = len({tuple(c['chords']) for c in candidates})
            facts['heldoutF1'] = mean(c['heldoutF1'] for c in candidates)
            for metric in candidates[0]['metrics']:
                values = [c['metrics'][metric] for c in candidates if c['metrics'][metric] is not None]
                facts[metric] = mean(values) if values else None
            if len(judges) == 2 and all(all(tuple(c['chords']) in j for c in candidates) for j in judges):
                scores = [[mean(j[tuple(c['chords'])].values()) for j in judges] for c in candidates]
                per_candidate = [mean(s) for s in scores]
                facts.update(blindMean=mean(per_candidate), blindTop1=per_candidate[0],
                             blindBest3=max(per_candidate), blindWorst3=min(per_candidate),
                             order0=mean(s[0] for s in scores), order1=mean(s[1] for s in scores),
                             orderSensitivity=mean(abs(s[0] - s[1]) for s in scores))
                facts['dimensions'] = {k: mean(j[tuple(c['chords'])][k] for c in candidates for j in judges) for k in RUBRIC}
        result['arms'][name] = facts
    result['hybrid2ChangedSet'] = None
    result['hybrid2ChangedRanking'] = None
    if all(case['arms'][a]['status'] == 'ok' for a in ('hybrid1', 'hybrid2')):
        result['hybrid2ChangedSet'] = set(case['arms']['hybrid1']['ids']) != set(case['arms']['hybrid2']['ids'])
        result['hybrid2ChangedRanking'] = case['arms']['hybrid1']['ids'] != case['arms']['hybrid2']['ids']
    if all(tuple(case['original']) in j and tuple(case['control']) in j for j in judges) and len(judges) == 2:
        fit = ('continuity', 'melodyFit', 'retainsIdentity')
        result['controls'] = {name: mean(j[tuple(case[field])][k] for j in judges for k in fit)
                              for name, field in [('original', 'original'), ('perturbation', 'control')]}
    return result


def grouped_values(cases, arm, metric):
    groups = defaultdict(list)
    for case in cases:
        value = case['arms'][arm].get(metric)
        if isinstance(value, (float, int)):
            groups[case['tuneGroup']].append(value)
    return {name: mean(values) for name, values in groups.items()}


def paired_interval(cases, left, right, metric='blindMean'):
    shared = [c for c in cases if c['arms'][left].get(metric) is not None and c['arms'][right].get(metric) is not None]
    a, b = grouped_values(shared, left, metric), grouped_values(shared, right, metric)
    deltas = [a[key] - b[key] for key in sorted(a.keys() & b.keys())]
    if not deltas:
        return {'cases': 0, 'tunes': 0}
    randomizer = random.Random(731)
    samples = sorted(mean(randomizer.choices(deltas, k=len(deltas))) for _ in range(5000))
    return {'cases': len(shared), 'tunes': len(deltas), 'meanDifference': mean(deltas),
            'interval95': [samples[125], samples[4874]],
            'winRateByTune': mean(d > 0 for d in deltas), 'tiesByTune': sum(d == 0 for d in deltas)}


def summarize(report):
    cases = [case_facts(c) for c in report['cases']]
    summary = {'completedCases': len(cases), 'tunes': len({c['tuneGroup'] for c in cases}),
               'datasetSha256': report.get('datasetSha256'), 'protocolVersion': report.get('protocolVersion'),
               'preparationFailures': report.get('preparationFailures', []), 'arms': {}, 'paired': {},
               'generationFailures': [], 'judgeFailures': []}
    metrics = ('blindMean', 'blindTop1', 'blindBest3', 'blindWorst3', 'order0', 'order1', 'orderSensitivity',
               'melodySupportDelta', 'pitchDistanceDelta', 'bassMotionDelta', 'performanceProfileDelta',
               'heldoutF1', 'changedSlots', 'costUsd', 'seconds')
    for arm in ARMS:
        data = {'success': sum(c['arms'][arm]['status'] == 'ok' for c in cases),
                'failed': sum(c['arms'][arm]['status'] != 'ok' for c in cases),
                'judgedTwice': sum('blindMean' in c['arms'][arm] for c in cases),
                'validCandidates': sum(sum(p['metrics']['validSparsePatch'] for p in c['arms'][arm].get('candidates', [])) for c in report['cases'])}
        for metric in metrics:
            grouped = grouped_values(cases, arm, metric)
            data[metric] = mean(grouped.values()) if grouped else None
        dimensions = defaultdict(list)
        for case in cases:
            for dimension, value in case['arms'][arm].get('dimensions', {}).items():
                dimensions[(dimension, case['tuneGroup'])].append(value)
        data['dimensions'] = {dimension: mean(mean(values) for (name, _), values in dimensions.items() if name == dimension)
                              for dimension in RUBRIC if any(name == dimension for name, _ in dimensions)}
        summary['arms'][arm] = data
    for i, left in enumerate(ARMS):
        for right in ARMS[i + 1:]:
            summary['paired'][f'{left}-{right}'] = paired_interval(cases, left, right)
    summary['pairedByOrder'] = {metric: {f'{left}-{right}': paired_interval(cases, left, right, metric)
                                        for i, left in enumerate(ARMS) for right in ARMS[i + 1:]}
                               for metric in ('order0', 'order1')}
    sets = [c['hybrid2ChangedSet'] for c in cases if c['hybrid2ChangedSet'] is not None]
    summary['hybrid2ChangedSetRate'] = mean(sets) if sets else None
    rankings = [c['hybrid2ChangedRanking'] for c in cases if c['hybrid2ChangedRanking'] is not None]
    summary['hybrid2ChangedRankingRate'] = mean(rankings) if rankings else None
    summary['hybridComparisonCases'] = len(sets)
    summary['hybrid2ChangedSetCount'] = sum(sets)
    summary['hybrid2ChangedRankingCount'] = sum(rankings)
    controls = [c['controls'] for c in cases if 'controls' in c]
    summary['controls'] = {'cases': len(controls),
                           'originalFit': mean(c['original'] for c in controls) if controls else None,
                           'perturbationFit': mean(c['perturbation'] for c in controls) if controls else None,
                           'originalHigherCount': sum(c['original'] > c['perturbation'] for c in controls)}
    summary['candidatePositions'] = sum(len(a.get('candidates', [])) for c in report['cases'] for a in c['arms'].values())
    summary['uniqueCandidateVersions'] = sum(len({tuple(p['chords']) for a in c['arms'].values() for p in a.get('candidates', [])}) for c in report['cases'])
    summary['actualCostUsd'] = sum(a.get('incrementalCostUsd', a['costUsd']) for c in report['cases'] for a in c['arms'].values())
    summary['actualCostUsd'] += sum(j.get('response', {}).get('cost_usd', j.get('costUsd', 0)) for c in report['cases'] for j in c['judges'])
    summary['actualCostUsd'] = round(summary['actualCostUsd'], 8)
    summary['recordedCalls'] = sum('response' in a or a['status'] == 'failed' for c in report['cases']
                                  for name, a in c['arms'].items() if name != 'local') + sum(len(c['judges']) for c in report['cases'])
    for case in report['cases']:
        for name, arm in case['arms'].items():
            if arm['status'] != 'ok':
                summary['generationFailures'].append({'id': case['id'], 'arm': name, 'status': arm['status'], 'error': arm['error']})
        for index, judge in enumerate(case['judges']):
            if judge['status'] != 'ok':
                summary['judgeFailures'].append({'id': case['id'], 'ordering': index, 'error': judge['error']})
    summary['ledger'] = report.get('ledger', {})
    summary['cases'] = cases  # Only numeric results/source IDs, no original musical data.
    return summary


def markdown(summary):
    lines = ['# Reharmonization comparison results', '',
             f"{summary['completedCases']} passages across {summary['tunes']} tune groups; "
             f"{summary['candidatePositions']} candidate positions, {summary['uniqueCandidateVersions']} distinct versions within passages.", '',
             'Tune-balanced means. Blind scores are automated 0–4 ratings, not listening results.', '',
             '| Condition | Completed | Judged twice | Blind mean | First choice | Best of 3 | Worst of 3 | Seconds | USD per passage |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    def fmt(value, places=3): return '—' if value is None else f'{value:.{places}f}'
    for arm, values in summary['arms'].items():
        lines.append(f"| {arm} | {values['success']}/{summary['completedCases']} | {values['judgedTwice']} | " +
                     ' | '.join(fmt(values[m]) for m in ('blindMean', 'blindTop1', 'blindBest3', 'blindWorst3', 'seconds', 'costUsd')) + ' |')
    lines += ['', 'Hybrid 2 includes its shared Hybrid 1 cost and time. Actual batch cost counts that pass once.', '',
              '| Paired difference (left − right) | Mean | 95% tune bootstrap interval | Tunes |',
              '| --- | ---: | --- | ---: |']
    for pair, item in summary['paired'].items():
        if item['tunes']:
            low, high = item['interval95']
            lines.append(f"| {pair} | {item['meanDifference']:.3f} | [{low:.3f}, {high:.3f}] | {item['tunes']} |")
    lines += ['', f"Actual batch cost: ${summary['actualCostUsd']:.6f}.", '',
              'Six exploratory pairwise intervals; no multiplicity correction. They quantify this automated judge, not human preference.', '',
              '## Rubric and presentation stability', '',
              '| Condition | Continuity | Melody fit | Useful change | Retained identity | Order 1 | Order 2 | Mean absolute order difference |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for arm, values in summary['arms'].items():
        lines.append(f'| {arm} | ' + ' | '.join(fmt(values['dimensions'].get(k)) for k in RUBRIC) + ' | ' +
                     ' | '.join(fmt(values[k]) for k in ('order0', 'order1', 'orderSensitivity')) + ' |')
    lines += ['', 'Order differences also include model sampling variation; this is not a pure causal estimate of position bias.', '',
              '## Descriptive secondary measurements', '',
              '| Condition | Strict melody support Δ | Pitch distance Δ | Bass motion Δ | Performance profile cosine Δ | F1 log likelihood | Changed slots |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for arm, values in summary['arms'].items():
        lines.append(f'| {arm} | ' + ' | '.join(fmt(values[k]) for k in ('melodySupportDelta', 'pitchDistanceDelta', 'bassMotionDelta',
                                                                      'performanceProfileDelta', 'heldoutF1', 'changedSlots')) + ' |')
    lines += ['', 'Δ is relative to the unchanged original. Lower motion means closer pitch classes/bass, not necessarily better harmony.',
              'Strict support counts chord tones only and can reward denser chords; a melody tension is not automatically an error.',
              'Performance-profile similarity is whole-excerpt descriptive evidence; the performance MIDI is not an expert chord answer.',
              'F1 log likelihood is higher when less negative. F1 and selecting F4 share ancestry; this is not fully independent validation.', '',
              '## Completion and controls', '',
              f"Hybrid 2 changed the candidate set in {summary['hybrid2ChangedSetCount']}/{summary['hybridComparisonCases']} passages; "
              f"changed the ordered list in {summary['hybrid2ChangedRankingCount']}/{summary['hybridComparisonCases']}."]
    control = summary['controls']
    lines += [f"Control fit (excluding useful change): original {fmt(control['originalFit'])}, semitone perturbation {fmt(control['perturbationFit'])}; "
              f"original higher in {control['originalHigherCount']}/{control['cases']} passages. A perturbation is not guaranteed to be musically wrong.", '',
              f"Preparation failures: {len(summary['preparationFailures'])}; generation failures/blocked arms: {len(summary['generationFailures'])}; "
              f"judgment failures: {len(summary['judgeFailures'])}."]
    if summary['generationFailures'] or summary['judgeFailures']:
        lines.append('')
    for failure in summary['generationFailures']:
        lines.append(f"- {failure['id']} / {failure['arm']}: {failure['error']}")
    for failure in summary['judgeFailures']:
        lines.append(f"- {failure['id']} / judge order {failure['ordering'] + 1}: {failure['error']}")
    lines += ['', 'Meta is both a selector and judge. No frontend choice follows automatically from these scores.', '']
    return '\n'.join(lines)


def detailed_html(report):
    esc = html.escape
    pieces = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Reharmonization comparison</title>',
              '<meta name="viewport" content="width=device-width,initial-scale=1">',
              '<style>body{font:15px system-ui;margin:2rem;line-height:1.5;background:#faf9f5;color:#222}table{width:100%;table-layout:fixed;border-collapse:collapse}td,th{border:1px solid #ccc;padding:12px;vertical-align:top}mark{background:#ffe48d}details{margin:1rem 0}summary{cursor:pointer;font-weight:650;padding:10px;background:#edece6}small{color:#555}.chords{font-family:monospace;overflow-wrap:anywhere}.score{font-weight:700;color:#333}p{max-width:100ch}th:first-child{width:8%}@media(max-width:700px){body{margin:1rem;font-size:12px}td,th{padding:5px}}</style>',
              '<h1>Four selectors · Three alternatives each</h1><p>Automated ratings, no listening claim. Yellow marks changed chords. Each column is a complete alternative to the original passage. F4 is the local selecting checkpoint; F1 is a related secondary scorer.</p>',
              '<p>Source: Row, Tang and Fazekas, <a href="https://zenodo.org/records/11264676">JAZZVAR</a> (CC BY-NC-SA 2.0). These derived musical inputs and outputs stay local and are not redistributed in the public repository.</p>']
    for case in report['cases']:
        maps = [rating_map(j) for j in case['judges']]
        pieces.append(f"<details><summary>{esc(case['tune'])} · {esc(case['id'])}</summary><p>Original: {esc(' | '.join(' '.join(case['original'][i:i+2]) for i in range(0,8,2)))}</p><p>Selected: bar 2 · at most two chord changes · {esc(case['request']['key'])}</p><table><tr><th>Condition</th><th>1</th><th>2</th><th>3</th></tr>")
        for name, arm in case['arms'].items():
            pieces.append(f'<tr><th>{name}</th>')
            if arm['status'] != 'ok':
                pieces.append(f"<td colspan=3>{esc(arm.get('error', arm['status']))}</td></tr>")
                continue
            for candidate in arm['candidates']:
                symbols = [f'<mark>{esc(c)}</mark>' if c != case['original'][i] else esc(c) for i,c in enumerate(candidate['chords'])]
                ratings = [mean(j[tuple(candidate['chords'])].values()) for j in maps if tuple(candidate['chords']) in j]
                score = f'{mean(ratings):.2f}/4 ({len(ratings)} ratings)' if ratings else 'Not rated'
                reason = next((c['reason'] for c in arm.get('response', {}).get('data', {}).get('choices', []) if c['id'] == candidate['id']), 'F4 contextual likelihood ranking')
                judge_reasons = []
                for index, judge in enumerate(case['judges']):
                    if judge['status'] != 'ok':
                        judge_reasons.append(f"Judge {index + 1}: failed")
                        continue
                    anonymous_id = next(key for key, chords in judge['mapping'].items() if chords == candidate['chords'])
                    rating = next(r for r in judge['response']['data']['ratings'] if r['id'] == anonymous_id)
                    judge_reasons.append(f"Judge {index + 1}: {rating['reason']}")
                pieces.append(f"<td><div class=chords>{' | '.join(' '.join(symbols[i:i+2]) for i in range(0,8,2))}</div><p class=score>{score}</p><small>{esc(reason)}</small><details><summary>Assessment reasons</summary>" +
                              ''.join(f'<p>{esc(reason)}</p>' for reason in judge_reasons) + '</details></td>')
            pieces.append('</tr>')
        pieces.append('</table></details>')
    return '\n'.join([*pieces, '</html>'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'summary', 'markdown', 'html'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if not all(p.is_absolute() for p in vars(args).values()):
        parser.error('Use absolute paths')
    if any(p.exists() for p in (args.summary, args.markdown, args.html)):
        parser.error('Preserve existing reports; use new paths')
    report = json.loads(args.input.read_text())
    summary = summarize(report)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    args.markdown.write_text(markdown(summary))
    args.html.write_text(detailed_html(report))
    print(markdown(summary))


if __name__ == '__main__':
    main()
