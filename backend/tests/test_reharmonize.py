"""Sparse search, real native-tool envelopes and charge settlement; no paid/network calls."""
import json
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.models.reharmonize import ReharmRequest
from app.services import llm, reharmonize_agent as agent
from app.services.reharmonize import chord, context_window, convention_preference, search
from tests.test_llm import LLMTestCase, FakeTransport


def request(**overrides):
    return ReharmRequest(**{
        "key": "C major", "context": [
            {"measure": 0, "chords": ["Cmaj7", "Am7"]},
            {"measure": 1, "chords": ["Dm7", "G7"]},
            {"measure": 2, "chords": ["Cmaj7", None]}],
        "selectedSlots": [{"measureIndex": 1, "slotIndex": 0}, {"measureIndex": 1, "slotIndex": 1}],
        **overrides})


def tool_response(name, args):
    return {"id": "completion-1", "model": "muse-spark-1.3",
            "choices": [{"finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call-1", "type": "function", "function": {
                    "name": name, "arguments": json.dumps(args)}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100}}


class FakeScorer:
    label = "test-checkpoint"

    def score(self, candidates):
        return [c.model_copy(update={"modelScore": -i - .5}) for i, c in enumerate(candidates)]


class SearchTests(unittest.TestCase):
    def test_sparse_unique_and_original_immutable(self):
        for maximum in (1, 2):
            req = request(maxChanges=maximum)
            original = req.model_dump_json()
            for family in ("common_tones", "modal", "dominant"):
                candidates = search(req, family)
                self.assertGreaterEqual(len(candidates), 2)
                self.assertEqual(len({c.id for c in candidates}), len(candidates))
                for candidate in candidates:
                    self.assertLessEqual(len(candidate.changes), maximum)
                    for change in candidate.changes:
                        self.assertEqual(change.address.measureIndex, 1)
                        self.assertEqual(change.before, req.context[1].chords[change.address.slotIndex])
                        self.assertNotEqual(change.before, change.after)
            self.assertEqual(req.model_dump_json(), original)

    def test_extension_and_slash_pitch_classes_are_not_lost(self):
        self.assertEqual(chord("C7(b9)/Db")[1], {0, 1, 4, 7, 10})
        self.assertEqual(chord("Cmaj7/Db")[1], {0, 1, 4, 7, 11})
        self.assertEqual(chord("Cmaj9")[1], {0, 2, 4, 7, 11})
        with self.assertRaises(ValueError):
            chord("Cmadeup")
        req = request(context=[{"measure": 0, "chords": ["Dm7", "G7/B"]}],
                      selectedSlots=[{"measureIndex": 0, "slotIndex": 1}])
        self.assertTrue(all(c.changes[0].after.endswith('/B') for c in search(req, 'common_tones')))

    def test_parallel_mode_is_a_hard_candidate_constraint(self):
        req = request(mode="dorian")
        candidates = search(req, "modal")
        self.assertTrue(candidates)
        self.assertTrue(all("dorian" in change.modes for c in candidates for change in c.changes))

    def test_both_neighbors_change_the_mathematical_comparison(self):
        req = request(selectedSlots=[{"measureIndex": 1, "slotIndex": 1}])
        before = {c.id: c.mathScore for c in search(req, "dominant")}
        req.context[1].chords[0] = "Abmaj7"
        middle = {c.id: c.mathScore for c in search(req, "dominant")}
        self.assertNotEqual(before, middle)
        req.context[2].chords[0] = "Fm7"
        after = {c.id: c.mathScore for c in search(req, "dominant")}
        self.assertNotEqual(before, after)
        self.assertNotEqual(middle, after)

    def test_refuse_blanks_duplicate_targets_and_wide_selection(self):
        for selection in ([{"measureIndex": 2, "slotIndex": 1}],
                          [{"measureIndex": 0, "slotIndex": 0}] * 2,
                          [{"measureIndex": 200, "slotIndex": 0}]):
            with self.assertRaises(ValidationError):
                request(selectedSlots=selection)
        with self.assertRaises(ValidationError):
            request(context=[{"measure": 3, "chords": ["C", "G"]}])

    def test_context_window_preserves_known_bars_on_both_sides(self):
        req = request(context=[{"measure": i, "chords": ["C", "G"]} for i in range(64)],
                      selectedSlots=[{"measureIndex": 30, "slotIndex": 0}])
        self.assertEqual([bar.measure for bar in context_window(req)], list(range(22, 39)))

    def test_familiar_predominants_get_contextual_support_not_a_blanket_mode_bonus(self):
        resolving, reasons = convention_preference('C major', 'Dm7', 'Dm7b5', 'Am7', 'G7')
        unrelated, _ = convention_preference('C major', 'Dm7', 'Dm7b5', 'Am7', 'Bb')
        self.assertGreater(resolving, unrelated)
        self.assertTrue(any('predominant' in label for label in reasons))
        self.assertGreater(convention_preference('C major', 'F', 'Fm', 'C', 'G7')[0], 0)
        self.assertEqual(convention_preference('C major', 'F', 'F#m7b5', 'C', 'Ab')[0], 0)

    def test_tritone_and_backdoor_preferences_require_their_resolution(self):
        self.assertGreater(convention_preference('C major', 'G7', 'Db7', 'Dm7', 'Cmaj7')[0], 0)
        self.assertEqual(convention_preference('C major', 'G7', 'Db7', 'Dm7', 'Am7')[0], 0)
        prepared = convention_preference('C major', 'G7', 'Bb7', 'Fm7', 'Cmaj7')
        unprepared = convention_preference('C major', 'G7', 'Bb7', 'Dm7', 'Cmaj7')
        self.assertGreater(prepared[0], unprepared[0])
        self.assertIn('Backdoor dominant to I', prepared[1])
        self.assertNotIn('Backdoor dominant to I', convention_preference('C major', 'G7', 'Bb7', 'Fm7', 'Em7')[1])

    def test_priors_transpose_and_support_minor_dorian_and_local_lydian(self):
        self.assertEqual(convention_preference('C major', 'Dm7', 'Dm7b5', 'Am7', 'G7'),
                         convention_preference('D major', 'Em7', 'Em7b5', 'Bm7', 'A7'))
        self.assertGreater(convention_preference('C minor', 'Fm', 'F', 'Cm', 'G7')[0], 0)
        self.assertGreater(convention_preference('C major', 'Dm', 'D', 'C', 'G')[0], 0)
        self.assertEqual(convention_preference('C major', 'Dm', 'D', 'Am', 'G')[0], 0)

    def test_familiar_options_reach_the_shortlist_with_the_contextual_prior(self):
        candidates = search(request(), 'modal')
        borrowed = next(c for c in candidates if c.changes[0].after == 'Dm7b5')
        self.assertGreater(borrowed.conventionScore, 0)
        with patch('app.services.reharmonize.convention_preference', return_value=(0, [])):
            no_prior = search(request(), 'modal', limit=100)
        self.assertNotIn(borrowed.id, {c.id for c in no_prior})
        self.assertTrue(any('Resolving tritone substitute' in change.conventions
                            for c in search(request(), 'dominant') for change in c.changes))

    def test_empty_half_bars_do_not_hide_the_previous_or_following_harmony(self):
        dense = request(context=[{'measure': 0, 'chords': ['Dm7', 'G7']}, {'measure': 1, 'chords': ['Cmaj7', None]}],
                        selectedSlots=[{'measureIndex': 0, 'slotIndex': 1}])
        sparse = request(context=[{'measure': i, 'chords': [symbol, None]}
                                  for i, symbol in enumerate(['Dm7', 'G7', 'Cmaj7'])],
                         selectedSlots=[{'measureIndex': 1, 'slotIndex': 0}])
        def facts(req):
            return {c.changes[0].after: (c.mathScore, c.conventionScore, c.changes[0].conventions)
                    for c in search(req, 'dominant')}
        self.assertEqual(facts(dense), facts(sparse))


class NativeToolsTests(LLMTestCase):
    def test_tool_turn_has_auto_choice_and_settles_usage(self):
        transport = FakeTransport(tool_response("search_substitutions", {"family": "modal"}))
        client = self.client(transport)
        with llm.track_call_costs() as costs:
            reply = client.chat_tools([{"role": "user", "content": "Compare chords."}], agent.TOOLS,
                                      label="reharm-test", max_request_usd=.15)
        self.assertEqual(reply.data['calls'][0]['arguments'], {"family": "modal"})
        self.assertEqual(transport.calls[0]['tool_choice'], 'auto')
        self.assertNotIn('response_format', transport.calls[0])
        self.assertGreater(costs.cost_usd, 0)
        self.assertEqual(costs.cost_usd, reply.cost_usd)
        self.assertEqual(json.loads(self.ledger_path.read_text())['entries'][0]['status'], 'settled')

    def test_reject_unknown_tool_and_invalid_arguments_after_settling(self):
        for name, args in (("write_score", {}), ("search_substitutions", {"family": "invented"}),
                           ("search_substitutions", {"family": "modal", "rewriteAll": True})):
            client = self.client(FakeTransport(tool_response(name, args)))
            with llm.track_call_costs() as costs, self.assertRaises(llm.LLMResponseError):
                client.chat_tools([{"role": "user", "content": "Compare."}], agent.TOOLS,
                                  label="bad-tool", max_request_usd=.15)
            self.assertGreater(costs.cost_usd, 0)
            self.assertEqual(json.loads(self.ledger_path.read_text())['entries'][-1]['status'], 'failed')

    def test_tool_definitions_count_toward_reservation(self):
        transport = FakeTransport(tool_response('search_substitutions', {'family': 'modal'}))
        with self.assertRaises(llm.BudgetExceeded):
            self.client(transport).chat_tools([{"role": "user", "content": "Compare"}], agent.TOOLS,
                                             label="cap", max_request_usd=.0001)
        self.assertEqual(transport.calls, [])

    def test_agent_explores_then_offers_only_searched_candidates(self):
        req = request()
        calls = []

        def transport(body):
            calls.append(body)
            if len(calls) < 3:
                family = ['common_tones', 'modal'][len(calls) - 1]
                response = tool_response('search_substitutions', {'family': family})
            else:
                pool = [c for msg in body['messages'] if msg['role'] == 'tool'
                        for c in json.loads(msg['content']).get('candidates', [])]
                ids = list(dict.fromkeys(c['id'] for c in pool))[:3]
                response = tool_response('offer_candidates', {'candidateIds': ids})
            return response, {'x-request-id': f'req-{len(calls)}'}

        client = self.client(transport)
        original = req.model_dump_json()
        with llm.track_call_costs() as costs:
            result = agent.propose(req, client=client, scorer=FakeScorer())
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(result.toolCalls, ['search_substitutions', 'search_substitutions', 'offer_candidates'])
        self.assertEqual(result.requestIds, ['req-1', 'req-2', 'req-3'])
        self.assertAlmostEqual(result.costUsd, costs.cost_usd)
        self.assertEqual(calls[1]['messages'][-2]['role'], 'assistant')
        self.assertEqual(calls[1]['messages'][-1]['tool_call_id'], 'call-1')
        self.assertEqual(req.model_dump_json(), original)
        offered = [c for message in calls[-1]['messages'] if message['role'] == 'tool'
                   for c in json.loads(message['content']).get('candidates', [])]
        self.assertTrue(any(c['conventionScore'] > 0 and c['changes'][0]['conventions'] for c in offered))
        facts_by_id = {c['id']: c for c in offered}
        self.assertTrue(all(c.model_dump() == facts_by_id[c.id] for c in result.candidates))

    def test_repeated_searches_stop_at_four_turns(self):
        transport = FakeTransport(tool_response('search_substitutions', {'family': 'common_tones'}))
        with self.assertRaisesRegex(llm.LLMResponseError, 'four-turn'):
            agent.propose(request(), client=self.client(transport), scorer=FakeScorer())
        self.assertEqual(len(transport.calls), 4)

    def test_offer_before_search_and_unrecognized_id_are_not_fallbacks(self):
        transport = FakeTransport(tool_response('offer_candidates', {'candidateIds': ['fake-a', 'fake-b', 'fake-c']}))
        with self.assertRaises(llm.LLMResponseError):
            agent.propose(request(), client=self.client(transport), scorer=FakeScorer())

    def test_route_settles_prior_calls_on_later_failure(self):
        from app.routes.reharmonize import reharmonize_route
        from fastapi import HTTPException
        client = self.client(FakeTransport(tool_response('search_substitutions', {'family': 'common_tones'})))
        with patch('app.routes.reharmonize.limits.limiter') as limiter, \
                patch.object(agent.llm, 'get_client', return_value=client), \
                patch.object(agent, 'ContextScorer', return_value=FakeScorer()):
            with self.assertRaises(HTTPException) as caught:
                reharmonize_route(request())
            self.assertEqual(caught.exception.status_code, 502)
            self.assertGreater(limiter.settle.call_args.args[1], 0)
