"""Experiment validity checks. No paid API or downloaded corpus required."""
import importlib.util
import io
import json
import threading
from pathlib import Path
import unittest

import mido

from app.models.reharmonize import ReharmCandidate, Change, Slot


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / 'agent' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


data = load('reharm_eval_data')
experiment = load('compare_reharmonization')
reporter = load('report_reharmonization')


def fixture():
    symbols = ['C', 'Am7', 'Dm7', 'G7', 'Cmaj7', 'Am7', 'Dm7', 'G7']
    candidates = [ReharmCandidate(id=name, family='dominant',
                  changes=[Change(address=Slot(measureIndex=1, slotIndex=1), before='G7', after=after,
                                  commonTones=2, modes=[], conventions=['test fact'])],
                  pitchDistance=1, originalPitchDistance=1, bassMotion=1, originalBassMotion=1,
                  mathScore=1, conventionScore=.3, modelScore=-1)
                  for name, after in [('a', 'Db7'), ('b', 'Bb7'), ('c', 'G7b9')]]
    case = {'id': 'synthetic', 'tune': 'Synthetic', 'tuneGroup': 'synthetic', 'request': {'key': 'C major', 'maxChanges': 2,
            'context': [{'measure': i, 'chords': symbols[i*2:i*2+2]} for i in range(4)],
            'selectedSlots': [{'measureIndex': 1, 'slotIndex': 0}, {'measureIndex': 1, 'slotIndex': 1}]},
            'melodyProfiles': [[1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]] * 8,
            'variationProfile': [1 / 12] * 12}
    versions = {c.id: [*symbols[:3], c.changes[0].after, *symbols[4:]] for c in candidates}
    prepared = {'case': case, 'candidates': candidates, 'local': ['a', 'b', 'c'], 'modelUsed': 'fake',
                'original': symbols, 'versions': versions, 'heldoutF1': {c.id: -2 for c in candidates},
                'searchSeconds': .1, 'localScoreSeconds': .2}
    return prepared


class DataTests(unittest.TestCase):
    def test_exact_pitch_sets_and_real_bass_do_not_silently_simplify(self):
        self.assertEqual(data.exact_symbol([(0, 2, n) for n in (48, 60, 64, 67)], .125), 'C')
        self.assertEqual(data.exact_symbol([(0, 2, n) for n in (45, 60, 64, 67)], .125), 'Am7')
        with self.assertRaises(ValueError):
            data.exact_symbol([(0, 2, n) for n in (48, 49, 50, 51)], .125)

    def test_midi_tracks_preserve_pitch_time_and_reject_unclosed_notes(self):
        midi = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack([mido.MetaMessage('track_name', name='Melody'),
                               mido.Message('note_on', note=60, velocity=80),
                               mido.Message('note_off', note=60, time=480)])
        midi.tracks.append(track)
        output = io.BytesIO(); midi.save(file=output)
        self.assertEqual(data.midi_tracks(output.getvalue())[0]['notes'], [(0, 1, 60)])
        track.pop(); output = io.BytesIO(); midi.save(file=output)
        with self.assertRaisesRegex(ValueError, 'Unclosed'):
            data.midi_tracks(output.getvalue())

    def test_reference_profiles_transpose_but_never_claim_beat_alignment(self):
        self.assertEqual(data.profile([(0, 1, 62), (1, 2, 64)], 0, 2, -2), [.5, 0, .5, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(data.tune_group("AIN'T MISBEHAVIN'"), data.tune_group("Ain't Misbehavin' - Live"))


class ExperimentTests(unittest.TestCase):
    def test_requested_stop_does_not_reserve_or_send_another_call(self):
        class Client:
            def chat_json(self, *args, **kwargs):
                raise AssertionError('A stopped experiment must not call its client')
        event = threading.Event(); event.set()
        record = experiment.run_case(fixture(), experiment.StoppableClient(Client(), event))
        self.assertEqual(record['arms']['meta']['status'], 'cancelled')
        self.assertEqual(record['arms']['hybrid1']['status'], 'cancelled')
        self.assertEqual(record['arms']['hybrid2']['status'], 'blocked')
        self.assertTrue(all(j['status'] == 'cancelled' and j['costUsd'] == 0 for j in record['judges']))
        summary = reporter.summarize({'cases': [record]})
        self.assertEqual(summary['recordedCalls'], 0)
        self.assertEqual(summary['actualCostUsd'], 0)

    def test_meta_only_has_no_learned_scores_and_hybrid_review_shares_first_choices(self):
        p = fixture()
        meta = experiment.selector_payload(p['case'], p['candidates'], learned=False)
        self.assertNotIn('modelScore', json.dumps(meta))
        prior = {'choices': [{'id': 'a', 'reason': 'first'}]}
        hybrid = experiment.selector_payload(p['case'], p['candidates'], learned=True, previous=prior)
        self.assertIn('modelScore', json.dumps(hybrid))
        self.assertEqual(hybrid['firstPass'], prior)
        with self.assertRaises(ValueError):
            experiment.validate_choices({'choices': [{'id': 'a'}] * 3}, ['a', 'b', 'c'])

    def test_blind_judge_deduplicates_identical_versions_and_hides_provenance(self):
        p = fixture()
        payload, mapping, _ = experiment.blind_payload(p['case'], p['original'], p['versions'], ['a', 'b', 'a', 'c'] * 3, 0)
        self.assertEqual(len(mapping), 5)  # Three unique versions plus original and control.
        self.assertEqual(len({tuple(v) for v in mapping.values()}), 5)
        for secret in ('modelScore', 'conventionScore', 'hybrid', 'local', 'performer'):
            self.assertNotIn(secret, json.dumps(payload))
        _, shuffled, _ = experiment.blind_payload(p['case'], p['original'], p['versions'], ['a', 'b', 'c'], 1)
        self.assertEqual({tuple(v) for v in mapping.values()}, {tuple(v) for v in shuffled.values()})

    def test_five_paid_stages_and_shared_hybrid_cost_are_accounted_without_double_billing(self):
        class Reply:
            cost_usd = .01
            def __init__(self, answer): self.data = answer
            def to_dict(self): return {'data': self.data, 'cost_usd': self.cost_usd}
        class Client:
            def __init__(self): self.calls = []
            def chat_json(self, messages, schema, **kwargs):
                self.calls.append(kwargs['label'])
                payload = json.loads(messages[-1]['content'])
                if 'reharm_judge' == kwargs['name']:
                    return Reply({'ratings': [{'id': c['id'], 'reason': 'test', **{k: 2 for k in experiment.RUBRIC}}
                                              for c in payload['candidates']]})
                return Reply({'choices': [{'id': c['id'], 'reason': 'test'} for c in payload['candidates'][:3]]})
        client = Client()
        report = experiment.run_case(fixture(), client)
        self.assertEqual(len(client.calls), 5)
        self.assertEqual(report['arms']['hybrid1']['costUsd'], .01)
        self.assertEqual(report['arms']['hybrid2']['costUsd'], .02)
        self.assertEqual(report['arms']['hybrid2']['incrementalCostUsd'], .01)
        self.assertTrue(all(c['metrics']['validSparsePatch'] for arm in report['arms'].values() for c in arm['candidates']))
        self.assertTrue(all(j['status'] == 'ok' for j in report['judges']))
        summary = reporter.summarize({'cases': [report]})
        self.assertAlmostEqual(summary['actualCostUsd'], .05)
        self.assertEqual(summary['candidatePositions'], 12)
        self.assertEqual(summary['uniqueCandidateVersions'], 3)
        self.assertEqual(summary['recordedCalls'], 5)
        self.assertTrue(all(a['blindMean'] == 2 for a in summary['arms'].values()))
        self.assertTrue(all(p['interval95'] == [0, 0] for p in summary['paired'].values()))


class ReportTests(unittest.TestCase):
    def test_paired_intervals_balance_tunes_and_use_only_common_cases(self):
        cases = [{'tuneGroup': 'many_windows', 'arms': {'local': {'blindMean': 4}, 'meta': {'blindMean': 2}}}] * 9
        cases += [{'tuneGroup': 'one_window', 'arms': {'local': {'blindMean': 0}, 'meta': {'blindMean': 2}}}]
        cases += [{'tuneGroup': 'failed', 'arms': {'local': {'blindMean': 4}, 'meta': {}}}]
        result = reporter.paired_interval(cases, 'local', 'meta')
        self.assertEqual((result['cases'], result['tunes']), (10, 2))
        self.assertEqual(result['meanDifference'], 0)  # Not the window-weighted +1.6.
        self.assertEqual(result['interval95'], [-2, 2])

    def test_partial_judgment_does_not_become_a_two_order_score(self):
        p = fixture()
        candidate = {'chords': p['versions']['a'], 'metrics': {'validSparsePatch': True}, 'heldoutF1': -2}
        _, mapping, control = experiment.blind_payload(p['case'], p['original'], p['versions'], ['a'], 0)
        ratings = [{'id': key, **{k: 3 for k in experiment.RUBRIC}} for key in mapping]
        record = {**p['case'], 'original': p['original'], 'control': control,
                  'arms': {arm: {'status': 'ok', 'costUsd': 0, 'seconds': 1, 'ids': ['a'], 'candidates': [candidate]} for arm in experiment.ARMS},
                  'judges': [{'status': 'ok', 'mapping': mapping, 'response': {'data': {'ratings': ratings}}},
                             {'status': 'failed', 'error': 'output limit'}]}
        facts = reporter.case_facts(record)
        self.assertTrue(all('blindMean' not in a for a in facts['arms'].values()))
        self.assertNotIn('controls', facts)
