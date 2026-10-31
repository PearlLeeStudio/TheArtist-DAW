"""Compare local checkpoint rankings on frozen pools, without paid API calls."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from statistics import mean


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('backend', 'input', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if not all(p.is_absolute() for p in vars(args).values()):
        parser.error('Use absolute paths')
    if args.output.exists():
        parser.error('Preserve previous results')
    sys.path.insert(0, str(args.backend))
    import torch
    from app.models.reharmonize import ReharmCandidate, ReharmRequest
    from app.services.reharmonize import ContextScorer, chord
    from compare_reharmonization import deterministic_metrics, versions
    from rank_reharmonization import balanced, judge_scores
    torch.set_num_threads(2)
    source = json.loads(args.input.read_text())
    keys = ('ft_f1', 'ft_f1_v2', 'ft_f2', 'ft_f3', 'ft_f4')
    result = {'scope': 'Fixed original mathematical pools; local rankings only; original-judge overlap is incomplete and selection-biased.',
              'datasetSha256': source['datasetSha256'], 'models': list(keys), 'cases': []}
    for case in source['cases']:
        record = {'id': case['id'], 'tuneGroup': case['tuneGroup'], 'models': {}}
        scores = judge_scores(case)
        for key in keys:
            request = ReharmRequest(**{**case['request'], 'modelKey': key})
            pool = [ReharmCandidate(**c) for c in case['pool']]
            ranked = ContextScorer(request).score(pool)
            original, selected = versions(request, ranked[:2])
            if key == 'ft_f4' and [c.id for c in ranked[:2]] != case['arms']['local']['ids'][:2]:
                raise ValueError('F4 ranking failed to reproduce the frozen reference')
            picks = []
            for candidate in ranked[:2]:
                changes = [chord(c.after) for c in candidate.changes]
                variant = tuple(selected[candidate.id])
                picks.append({'id': candidate.id, 'chords': list(variant), 'modelScore': candidate.modelScore,
                              'changedChordToneCount': mean(len(c[1]) for c in changes),
                              'alteredQualityShare': mean('#' in c[3] or 'b' in c[3] for c in changes),
                              'extendedQualityShare': mean(any(n in c[3] for n in ('9', '11', '13')) for c in changes),
                              'originalJudgeScore': mean(scores[variant].values()) if scores and variant in scores else None,
                              'metrics': deterministic_metrics(case, original, list(variant))})
            record['models'][key] = picks
        result['cases'].append(record)
    summary = {}
    for key in keys:
        rows = [{'id': c['id'], 'tuneGroup': c['tuneGroup'],
                 **{m: mean(p[m] for p in c['models'][key]) for m in ('changedChordToneCount', 'alteredQualityShare', 'extendedQualityShare')},
                 'melodySupportDelta': mean(p['metrics']['melodySupportDelta'] for p in c['models'][key])}
                for c in result['cases']]
        summary[key] = {m: balanced(rows, lambda r, m=m: r[m])['mean'] for m in ('changedChordToneCount', 'alteredQualityShare', 'extendedQualityShare', 'melodySupportDelta')}
        summary[key]['originalJudgeCoverage'] = sum(p['originalJudgeScore'] is not None for c in result['cases'] for p in c['models'][key])
    result['summary'] = summary
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
