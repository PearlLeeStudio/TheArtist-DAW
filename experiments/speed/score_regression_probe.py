"""One paid Meta reading per public fixture, replayed through both orchestration versions.

Supply the pre-speed score_verification.py on stdin. Stores only structural
diagnostics and equality results, never document text or credentials.
"""
import argparse
import base64
import copy
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.out.is_absolute():
        parser.error('--out must be absolute')
    from app.services import score_import, score_verification, llm
    from app.models.score_import import ScoreImportRequest
    legacy = types.ModuleType('reference_score_verification')
    legacy.__file__ = score_verification.__file__
    sys.modules[legacy.__name__] = legacy
    exec(compile(sys.stdin.read(), legacy.__file__, 'exec'), legacy.__dict__)
    rows = []
    root = Path(score_import.__file__).resolve().parents[2]
    client = llm.get_client()
    for name in ('vector-score-c.pdf', 'vector-score-f.pdf'):
        req = ScoreImportRequest(filename=name, mimeType='application/pdf', engine='verified',
                                mode='infer_harmony', dataBase64=base64.b64encode(
                                    (root / 'tests/fixtures' / name).read_bytes()).decode())
        recorded = []
        calls = []

        class ReplayClient:
            config = client.config

            def chat_json(self, *args, **kwargs):
                calls.append(copy.deepcopy((args, kwargs)))
                if not recorded:
                    recorded.append(client.chat_json(*args, **kwargs))
                return copy.deepcopy(recorded[0])

        attachment = score_import._attachment(req)
        with patch.object(score_import, 'get_client', return_value=ReplayClient()):
            optimized = score_verification.import_verified_score(req, attachment)
            reference = legacy.import_verified_score(req, attachment)
        assert len(calls) == 2 and calls[0] == calls[1], 'Request body/options changed'
        assert optimized.model_dump() == reference.model_dump(), 'Same Meta response produced different import'
        raw = recorded[0]
        rejection = None
        try:
            draft = score_import._validated_draft(copy.deepcopy(raw))
            score_import._check_provenance(req.mode, raw, draft)
            score_import._require_usable(req.mode, draft)
        except (llm.LLMError, score_import.ScoreInputError) as exc:
            rejection = dict(kind=getattr(exc, 'kind', type(exc).__name__), message=str(exc))
        row = dict(fixture=name, real_meta_calls=1, request_id=raw.request_id,
                   request_and_options_identical=True, import_result_identical=True,
                   verification=optimized.verification.status, measures=len(optimized.measures),
                   meta_complete=raw.data.get('complete'), meta_measures=len(raw.data.get('measures', [])),
                   meta_bars_with_chords=sum(bool(m.get('chords')) for m in raw.data.get('measures', [])),
                   rejection=rejection)
        rows.append(row)
        print(json.dumps(row), flush=True)
    args.out.write_text(json.dumps(rows, indent=2) + '\n')


if __name__ == '__main__':
    main()
