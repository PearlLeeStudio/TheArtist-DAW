import copy
import unittest
from unittest.mock import Mock, patch

from app.models.plan import PlanRequest
from app.services import planner
from app.services.llm import Ledger, LLMClient, LLMConfig
from tests.test_planner import Replies, completion

PLAN = {'sections': [
    {'type': 'verse', 'bars': 8, 'cadence': 'half', 'reason': 'Open the phrase', 'cites': []},
    {'type': 'chorus', 'bars': 8, 'cadence': 'authentic', 'reason': 'Resolve the hook', 'cites': []},
]}
CHORDS = {'sections': [
    {'index': 0, 'bars': [['Cmaj7', 'Am7'], ['Dm7', 'G7']] * 4},
    {'index': 1, 'bars': [['Fmaj7', 'Em7'], ['G7', 'C']] * 4},
]}


class MetaComposerTest(unittest.TestCase):
    def run_form(self, payload):
        ledger = Mock(spec=Ledger)
        ledger.cap_usd = 25.0
        ledger.reserve.return_value = 'test-reservation'
        ledger.settle.return_value = .003
        self.transport = Replies(completion(PLAN), completion(payload))
        client = LLMClient(LLMConfig(provider='meta', base_url='https://api.meta.ai/v1', model='muse-spark-1.3', api_key='test-only'), ledger, self.transport)
        events = []
        with patch.object(planner, '_client', return_value=client), patch.object(planner, 'compose_section') as own:
            result = planner.complete_form(PlanRequest(genre='pop', key='C major', targetBars=16, chordSource='meta'),
                                           lambda event, data: events.append((event, data)))
        own.assert_not_called()
        return result, events

    def test_meta_writes_every_chord_without_transformer_or_rule_replacements(self):
        result, events = self.run_form(CHORDS)
        self.assertEqual(result.status, 'ok', result.error)
        self.assertEqual(result.chordSource, 'meta')
        self.assertEqual([call.step for call in result.calls], ['plan_song', 'compose'])
        self.assertLessEqual(result.spendUsd, planner.MAX_RUN_USD)
        self.assertTrue(all(call.requestId for call in result.calls))
        self.assertEqual([s.startMeasure for s in result.sections], [0, 8])
        for i, section in enumerate(result.sections):
            self.assertEqual(section.modelUsed, 'muse-spark-1.3')
            self.assertEqual(section.rulesSlots, [])
            self.assertEqual(list(section.suggestions[0].chords.values()), CHORDS['sections'][i]['bars'])
        self.assertEqual(len([e for e, _ in events if e == 'generate_section']), 2)
        self.assertTrue(all(call['timeout'] <= planner.CALL_TIMEOUT_S for call in self.transport.calls))

    def test_missing_bars_and_unplayable_chords_leave_no_partial_sections(self):
        for kind in ('short', 'invalid', 'missing'):
            payload = copy.deepcopy(CHORDS)
            if kind == 'short': payload['sections'][1]['bars'].pop()
            if kind == 'invalid': payload['sections'][1]['bars'][0][0] = 'H major'
            if kind == 'missing': payload['sections'].pop()
            with self.subTest(kind=kind):
                result, events = self.run_form(payload)
                self.assertEqual(result.status, 'error')
                self.assertEqual(result.error.kind, 'invalid')
                self.assertEqual(result.sections, [])
                self.assertNotIn('generate_section', [e for e, _ in events])
                self.assertGreater(result.spendUsd, 0)

    def test_rules_button_cannot_silently_make_paid_meta_chords(self):
        with self.assertRaises(ValueError):
            PlanRequest(genre='pop', targetBars=16, planner='rules', chordSource='meta')
