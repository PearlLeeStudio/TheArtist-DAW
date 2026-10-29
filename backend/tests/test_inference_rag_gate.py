"""The build-level RAG gate: THEARTIST_DISABLE_RAG parsed by env_bool, off unless explicitly 0.

The dev wrapper exports THEARTIST_DISABLE_RAG=1, so every test sets or deletes the
variable itself. RAG_AVAILABLE is forced on so only the gate can stop construction.
"""

import os
import unittest
from unittest import mock

from app.models.schemas import Suggestion
from app.services import inference

VAR = "THEARTIST_DISABLE_RAG"


def suggestion(letter: str, *chords: str) -> Suggestion:
    return Suggestion(label=f"Option {letter} — test", chords={str(i): [c, c] for i, c in enumerate(chords)})


class RagGateTest(unittest.TestCase):
    def setUp(self):
        # A fresh environment and fresh module caches per test, restored afterwards
        self.patch(mock.patch.dict(os.environ))
        os.environ.pop(VAR, None)
        for name, value in (("_rag_retriever", None), ("_rag_llm_client", None),
                            ("_rag_init_failed", False), ("RAG_AVAILABLE", True)):
            self.patch(mock.patch.object(inference, name, value))
        for cache in (inference._theory_rerank_cache, inference._explanation_cache):
            self.patch(mock.patch.dict(cache, clear=True))

    def patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def never(self, name: str) -> mock.Mock:
        """Replace inference.<name> with a stub that must not be called."""
        stub = mock.Mock(name=name, side_effect=AssertionError(f"{name} must not run"))
        self.patch(mock.patch.object(inference, name, stub, create=True))
        return stub

    def test_unset_empty_or_1_disables_rag_without_constructing_anything(self):
        retriever, client = self.never("Retriever"), self.never("OpenAI")
        for value in (None, "", "1", " true "):
            with self.subTest(value=value):
                if value is None:
                    os.environ.pop(VAR, None)
                else:
                    os.environ[VAR] = value
                self.assertTrue(inference.rag_disabled())
                self.assertFalse(inference._should_use_rag("jazz"))
                self.assertEqual(inference._get_rag_services(), (None, None))
        # The old code swallowed a constructor error into _rag_init_failed, so the
        # (None, None) alone is not proof: nothing may have been attempted.
        retriever.assert_not_called()
        client.assert_not_called()
        self.assertFalse(inference._rag_init_failed)

    def test_0_enables_rag_and_constructs_the_services_once(self):
        os.environ[VAR] = "0"
        retriever = mock.Mock(name="Retriever", return_value=mock.sentinel.retriever)
        client = mock.Mock(name="OpenAI", return_value=mock.sentinel.client)
        self.patch(mock.patch.object(inference, "Retriever", retriever, create=True))
        self.patch(mock.patch.object(inference, "OpenAI", client, create=True))

        self.assertFalse(inference.rag_disabled())
        self.assertTrue(inference._should_use_rag("jazz"))
        self.assertFalse(inference._should_use_rag("pop"))  # the genre gate still applies
        services = inference._get_rag_services()
        self.assertEqual(services, (mock.sentinel.retriever, mock.sentinel.client))
        self.assertEqual(inference._get_rag_services(), services)  # cached, not rebuilt
        retriever.assert_called_once_with(collections=["berklee", "openmusictheory"])
        client.assert_called_once_with(base_url="http://localhost:11434/v1", api_key="ollama")

    def test_an_unparseable_value_raises_at_the_point_of_use(self):
        os.environ[VAR] = "maybe"
        retriever, client = self.never("Retriever"), self.never("OpenAI")
        for name, call in (("rag_disabled", inference.rag_disabled),
                           ("_should_use_rag", lambda: inference._should_use_rag("jazz")),
                           ("_get_rag_services", inference._get_rag_services)):
            with self.subTest(call=name), self.assertRaises(ValueError) as ctx:
                call()
            self.assertIn(VAR, str(ctx.exception))
        retriever.assert_not_called()
        client.assert_not_called()

    def test_disabled_helpers_skip_without_touching_rag(self):
        suggestions = [suggestion("A", "Dm7", "G7", "Cmaj7"), suggestion("B", "Fmaj7", "Bb7", "Cmaj7")]
        self.never("_get_rag_services")
        self.never("explain_transition")
        # Both axes off: the gate alone decides, and the order is the input order
        self.patch(mock.patch.object(inference, "PHYSICS_AVAILABLE", False))

        inference._theory_rerank_warmup(suggestions)
        self.assertIs(inference._attach_explanations(suggestions, [0, 1, 2]), suggestions)
        with self.assertLogs(inference.log, level="INFO") as logs:
            reranked = inference._rerank_composite(list(suggestions), genre="jazz")
        self.assertEqual([s.label for s in reranked], ["Option A — test", "Option B — test"])
        self.assertTrue(any("r2=off" in line for line in logs.output), logs.output)
        self.assertEqual(inference._theory_rerank_cache, {})
        self.assertTrue(all(s.explanations is None for s in suggestions))


if __name__ == "__main__":
    unittest.main()
