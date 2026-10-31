"""Recommendation-position gaps and top-two union coverage, without new model calls."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
from statistics import mean

ARMS = ('local', 'meta', 'hybrid1', 'hybrid2')
RUBRIC = ('continuity', 'melodyFit', 'usefulChange', 'retainsIdentity')


def judge_scores(case):
    if len(case['judges']) != 2 or any(j['status'] != 'ok' for j in case['judges']):
        return None
    maps = [{tuple(judge['mapping'][r['id']]): {k: r[k] for k in RUBRIC}
             for r in judge['response']['data']['ratings']} for judge in case['judges']]
    shared = maps[0].keys() & maps[1].keys()
    return {version: {k: mean(m[version][k] for m in maps) for k in RUBRIC} for version in shared}


def extract(case, batch):
    scores = judge_scores(case)
    result = {'id': case['id'], 'tuneGroup': case['tuneGroup'], 'batch': batch, 'arms': {}}
    versions_by_arm = {}
    for arm in ARMS:
        source = case['arms'][arm]
        if source['status'] != 'ok' or scores is None:
            continue
        versions = [tuple(c['chords']) for c in source['candidates']]
        if len(versions) != 3 or len(set(versions)) != 3 or not all(v in scores for v in versions):
            raise ValueError('Each completed arm must have three distinct, twice-rated versions')
        versions_by_arm[arm] = versions
        ratings = [mean(scores[v].values()) for v in versions]
        result['arms'][arm] = {'ranks': ratings, 'gap12': ratings[0] - ratings[1],
                               'gap23': ratings[1] - ratings[2],
                               'oracleLossTop2': max(ratings) - max(ratings[:2]),
                               'dimensions': {k: [scores[v][k] for v in versions] for k in RUBRIC}}
    if len(versions_by_arm) == 4:
        top2 = {v for versions in versions_by_arm.values() for v in versions[:2]}
        top3 = {v for versions in versions_by_arm.values() for v in versions}
        best2, best3 = (max(mean(scores[v].values()) for v in group) for group in (top2, top3))
        result['union'] = {'uniqueTop2': len(top2), 'uniqueTop3': len(top3),
                           'oracleBestTop2': best2, 'oracleBestTop3': best3,
                           'oracleLoss': best3 - best2, 'bestCovered': best2 == best3}
    return result


def balanced(rows, value):
    """Average repeated runs per passage, passages per tune; bootstrap tunes."""
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        number = value(row)
        if number is not None:
            grouped[row['tuneGroup']][row['id']].append(number)
    passages = {identity: mean(values) for group in grouped.values() for identity, values in group.items()}
    tunes = [mean(mean(values) for values in group.values()) for group in grouped.values()]
    if not tunes:
        return {'caseRuns': 0, 'passages': 0, 'tunes': 0, 'mean': None, 'interval95': None}
    rng = random.Random(731)
    draws = sorted(mean(rng.choices(tunes, k=len(tunes))) for _ in range(5000))
    return {'caseRuns': sum(len(v) for group in grouped.values() for v in group.values()),
            'passages': len(passages), 'tunes': len(tunes), 'mean': mean(tunes),
            'interval95': [draws[125], draws[4874]],
            'positivePassages': sum(v > 0 for v in passages.values()),
            'tiedPassages': sum(v == 0 for v in passages.values()),
            'negativePassages': sum(v < 0 for v in passages.values())}


def aggregate(rows, *, require_batches=1):
    output = {'arms': {}}
    for arm in ARMS:
        eligible = [row for row in rows if arm in row['arms']]
        batches = defaultdict(set)
        for row in eligible:
            batches[row['id']].add(row['batch'])
        eligible = [row for row in eligible if len(batches[row['id']]) == require_batches]
        output['arms'][arm] = {'ranks': [balanced(eligible, lambda r, i=i: r['arms'][arm]['ranks'][i]) for i in range(3)],
                               **{k: balanced(eligible, lambda r, k=k: r['arms'][arm][k])
                                  for k in ('gap12', 'gap23', 'oracleLossTop2')},
                               'dimensions': {k: [balanced(eligible, lambda r, k=k, i=i: r['arms'][arm]['dimensions'][k][i])['mean']
                                                  for i in range(3)] for k in RUBRIC}}
    union_rows = [row for row in rows if 'union' in row]
    batches = defaultdict(set)
    for row in union_rows:
        batches[row['id']].add(row['batch'])
    union_rows = [row for row in union_rows if len(batches[row['id']]) == require_batches]
    output['union'] = {key: balanced(union_rows, lambda r, key=key: r['union'][key])
                       for key in ('uniqueTop2', 'uniqueTop3', 'oracleBestTop2', 'oracleBestTop3', 'oracleLoss', 'bestCovered')}
    output['union']['uniqueTop2Range'] = [min((r['union']['uniqueTop2'] for r in union_rows), default=None),
                                         max((r['union']['uniqueTop2'] for r in union_rows), default=None)]
    output['union']['uniqueTop3Range'] = [min((r['union']['uniqueTop3'] for r in union_rows), default=None),
                                         max((r['union']['uniqueTop3'] for r in union_rows), default=None)]
    output['union']['caseRunsTop3FitsEight'] = sum(r['union']['uniqueTop3'] <= 8 for r in union_rows)
    output['union']['caseRunsWithLoss'] = sum(r['union']['oracleLoss'] > 0 for r in union_rows)
    output['union']['passagesWithAnyLoss'] = len({r['id'] for r in union_rows if r['union']['oracleLoss'] > 0})
    return output


def stability(original, repeat):
    originals = {c['id']: c for c in original['cases']}
    rows = []
    for new in repeat['cases']:
        old = originals[new['id']]
        if old['pool'] != new['pool'] or old['original'] != new['original'] or old['request'] != new['request']:
            raise ValueError(f"Pool/input changed in {new['id']}; not an identical-input repetition")
        row = {'id': new['id'], 'tuneGroup': new['tuneGroup'], 'arms': {}}
        for arm in ARMS:
            a, b = old['arms'][arm], new['arms'][arm]
            if a['status'] != 'ok' or b['status'] != 'ok':
                continue
            x, y = ([tuple(c['chords']) for c in v['candidates']] for v in (a, b))
            row['arms'][arm] = {'sameFirst': x[0] == y[0], 'sameTop2Set': set(x[:2]) == set(y[:2]),
                                'top2Overlap': len(set(x[:2]) & set(y[:2])) / 2,
                                'sameTop3Set': set(x) == set(y), 'sameOrdered3': x == y}
        before, after = judge_scores(old), judge_scores(new)
        if before is not None and after is not None:
            candidates = {tuple(c['chords']) for run in (old, new) for a in run['arms'].values() for c in a.get('candidates', [])}
            shared = before.keys() & after.keys() & candidates
            row['sharedVersionCount'] = len(shared)
            if shared:
                row['sharedVersionRatingDifference'] = mean(abs(mean(before[v].values()) - mean(after[v].values())) for v in shared)
        rows.append(row)
    return {'arms': {arm: {metric: balanced(rows, lambda r, arm=arm, metric=metric: r['arms'].get(arm, {}).get(metric))
                           for metric in ('sameFirst', 'sameTop2Set', 'top2Overlap', 'sameTop3Set', 'sameOrdered3')}
                     for arm in ARMS},
            'sharedVersionRatingDifference': balanced(rows, lambda r: r.get('sharedVersionRatingDifference')),
            'sharedVersions': sum(r.get('sharedVersionCount', 0) for r in rows), 'cases': rows}


def analyze(original, repeat=None):
    rows = [extract(c, 'original') for c in original['cases']]
    result = {'original': aggregate(rows), 'sourceDatasetSha256': original.get('datasetSha256')}
    if repeat is not None:
        if original['datasetSha256'] != repeat['datasetSha256']:
            raise ValueError('Dataset digest changed')
        new = [extract(c, 'repeat') for c in repeat['cases']]
        result.update(repeat=aggregate(new), combined=aggregate(rows + new, require_batches=2),
                      stability=stability(original, repeat))
        rows += new
    result['cases'] = rows  # No chord strings or source musical data in the public summary.
    return result


def compare_models(original, other):
    if original['datasetSha256'] != other['datasetSha256']:
        raise ValueError('Dataset digest changed')
    originals = {c['id']: c for c in original['cases']}
    def problem(case):
        return {'request': {k: v for k, v in case['request'].items() if k != 'modelKey'},
                'pool': [{k: v for k, v in c.items() if k != 'modelScore'} for c in case['pool']],
                **{k: case.get(k) for k in ('original', 'melodyProfiles', 'variationProfile')}}
    for case in other['cases']:
        if case['id'] not in originals or problem(originals[case['id']]) != problem(case):
            raise ValueError('Changed-model comparison must preserve musical inputs and mathematical pools')
    result = analyze(original)
    rows = [extract(c, 'comparison') for c in other['cases']]
    before = {r['id']: r for r in result['cases']}
    result['comparison'] = aggregate(rows)
    paired = []
    for row in rows:
        first = before[row['id']]
        values = {}
        for arm in ARMS:
            if arm in first['arms'] and arm in row['arms']:
                a, b = first['arms'][arm]['ranks'], row['arms'][arm]['ranks']
                values[arm] = {'top1': a[0] - b[0], 'top2Mean': mean(a[:2]) - mean(b[:2]),
                               'top3Mean': mean(a) - mean(b), 'worstTop2': min(a[:2]) - min(b[:2])}
        paired.append({'id': row['id'], 'tuneGroup': row['tuneGroup'], 'arms': values})
    result['modelDifferences'] = {arm: {metric: balanced(paired, lambda r, arm=arm, metric=metric: r['arms'].get(arm, {}).get(metric))
                                      for metric in ('top1', 'top2Mean', 'top3Mean', 'worstTop2')} for arm in ARMS}
    result['cases'] += rows
    return result


def markdown(result, label='Original', comparison_label='Compared model'):
    def fmt(value): return '—' if value is None else f'{value:.3f}'
    def interval(item): return '—' if item['interval95'] is None else '[' + ', '.join(fmt(v) for v in item['interval95']) + ']'
    lines = ['# Recommendation ranks and eight-position coverage', '',
             'Scores are blinded automated ratings on 0–4. Positions retain the selector’s recommendation order.',
             'Means average repeats within passage, then passages within tune. Intervals bootstrap tune groups (5,000 draws).',
             'Signed gaps can be negative; candidates have not been reordered using the judge. Intervals are exploratory, without multiplicity correction.', '']
    for name in ('original', 'repeat', 'combined', 'comparison'):
        if name not in result:
            continue
        batch = result[name]
        coverage = batch['arms']['local']['gap12']
        heading = label if name == 'original' else comparison_label if name == 'comparison' else name.capitalize()
        lines += [f'## {heading}', '',
                  f"{coverage['caseRuns']} case-runs across {coverage['passages']} passages and {coverage['tunes']} tune groups. "
                  + ('Combined results require successful ratings in both runs.' if name == 'combined' else '').rstrip(), '',
                  '| Method | Rank 1 | Rank 2 | Rank 3 | 1−2 | 95% interval | 2−3 | 95% interval |',
                  '| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |']
        for arm, values in batch['arms'].items():
            lines.append(f'| {arm} | ' + ' | '.join(fmt(v['mean']) for v in values['ranks']) +
                         f" | {fmt(values['gap12']['mean'])} | {interval(values['gap12'])} | {fmt(values['gap23']['mean'])} | {interval(values['gap23'])} |")
        lines += ['', '| Method | 1 > / = / < 2 (passages) | 2 > / = / < 3 (passages) | Best-of-3 missed by first two | Oracle score loss |',
                  '| --- | --- | --- | ---: | ---: |']
        for arm, values in batch['arms'].items():
            counts = [' / '.join(str(values[k][field]) for field in ('positivePassages', 'tiedPassages', 'negativePassages'))
                      if values[k]['passages'] else '—' for k in ('gap12', 'gap23')]
            loss = values['oracleLossTop2']
            lines.append(f"| {arm} | {' | '.join(counts)} | {loss.get('positivePassages', 0)}/{loss['passages']} | {fmt(loss['mean'])} |")
        union = batch['union']
        lines += ['', f"Eight selected positions contain {fmt(union['uniqueTop2']['mean'])} distinct musical versions on average "
                  f"(range {union['uniqueTop2Range'][0]}–{union['uniqueTop2Range'][1]}), versus {fmt(union['uniqueTop3']['mean'])} for all 12 positions.",
                  f"The eight-position union misses the 12-position oracle best in {union['caseRunsWithLoss']}/{union['oracleLoss']['caseRuns']} case-runs "
                  f"({union['passagesWithAnyLoss']} distinct passages). Mean oracle score loss: {fmt(union['oracleLoss']['mean'])}.",
                  'Coverage means retaining the highest automated score, including ties; it does not measure a listener’s chosen alternative.', '']
        if 'uniqueTop3Range' in union:
            lines += [f"Deduplicating all 12 positions first leaves {union['uniqueTop3Range'][0]}–{union['uniqueTop3Range'][1]} versions. "
                      f"All of them fit within eight cards in {union['caseRunsTop3FitsEight']}/{union['uniqueTop3']['caseRuns']} case-runs. "
                      'This retains every evaluated third choice in those cases, without another model call; it is not a guarantee for future inputs.', '']
    if 'stability' in result:
        values = result['stability']
        lines += ['## Selection repeatability', '', '| Method | Same first | Same top-two set | Top-two overlap | Same top-three set | Same ordered three |',
                  '| --- | ---: | ---: | ---: | ---: | ---: |']
        for arm, data in values['arms'].items():
            lines.append(f'| {arm} | ' + ' | '.join('—' if v['mean'] is None else f"{v['mean']:.1%}" for v in data.values()) + ' |')
        lines += ['', f"Mean absolute score difference for shared versions across runs: {fmt(values['sharedVersionRatingDifference']['mean'])}/4 "
                  f"over {values['sharedVersions']} shared passage-version pairs. This is judging variation, separate from changes in selection.", '']
    if 'modelDifferences' in result:
        lines += [f'## Paired difference: {label} minus {comparison_label}', '',
                  '| Method | First-two mean difference | 95% tune interval | First-choice difference | All-three mean difference |',
                  '| --- | ---: | --- | ---: | ---: |']
        for arm, values in result['modelDifferences'].items():
            lines.append(f"| {arm} | {fmt(values['top2Mean']['mean'])} | {interval(values['top2Mean'])} | "
                         f"{fmt(values['top1']['mean'])} | {fmt(values['top3Mean']['mean'])} |")
        lines += ['', 'Meta-only receives no local checkpoint score and identical inputs in both batches. Its difference reflects selection/judgment sampling, not a checkpoint effect.',
                  'The other differences also include run variation. These model batches are paired observations of the same passages, not independent new songs.', '']
    lines += ['Meta is both selector and judge. The material is chord context plus coarse melody profiles, with no listening or expert preference labels.',
              'A repeat on the same tunes is not an independent new-song test. No UI decision or new genre claim follows automatically.', '']
    return '\n'.join(line.rstrip() for line in lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original', 'summary', 'markdown'):
        parser.add_argument('--' + name, type=Path, required=True)
    alternative = parser.add_mutually_exclusive_group()
    alternative.add_argument('--repeat', type=Path)
    alternative.add_argument('--comparison', type=Path)
    parser.add_argument('--label', default='Original')
    parser.add_argument('--comparison-label', default='Compared model')
    args = parser.parse_args()
    if not all(p.is_absolute() for p in vars(args).values() if isinstance(p, Path)):
        parser.error('Use absolute paths')
    if args.summary.exists() or args.markdown.exists():
        parser.error('Preserve existing evidence; use new output paths')
    original = json.loads(args.original.read_text())
    result = (compare_models(original, json.loads(args.comparison.read_text())) if args.comparison else
              analyze(original, json.loads(args.repeat.read_text()) if args.repeat else None))
    args.summary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    args.markdown.write_text(markdown(result, args.label, args.comparison_label))
    print(markdown(result, args.label, args.comparison_label))


if __name__ == '__main__':
    main()
