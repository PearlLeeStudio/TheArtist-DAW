import pickle
import unittest
from unittest import mock

from app.services import score_pdf
from app.services.score_cache import ScoreCache
from tests.vector_score_fixture import build_vector_score_pdf


class ScoreCacheTests(unittest.TestCase):
    def test_payload_is_owned_by_each_caller(self):
        cache = ScoreCache()
        score = score_pdf.ParsedScore(warnings=["original"])
        cache.put(("score",), score)
        score.warnings.append("source edit")
        first = cache.get(("score",))
        first.warnings.append("caller edit")
        self.assertEqual(cache.get(("score",)).warnings, ["original"])

    def test_lru_size_and_entry_limits(self):
        score = score_pdf.ParsedScore()
        size = len(pickle.dumps(score, protocol=pickle.HIGHEST_PROTOCOL))
        for cache in (ScoreCache(max_entries=2), ScoreCache(max_bytes=size * 2)):
            cache.put((1,), score)
            cache.put((2,), score)
            self.assertIsNotNone(cache.get((1,)))
            cache.put((3,), score)
            self.assertIsNone(cache.get((2,)))
            self.assertIsNotNone(cache.get((1,)))
            self.assertIsNotNone(cache.get((3,)))
        cache = ScoreCache(max_bytes=size - 1)
        cache.put((1,), score)
        self.assertIsNone(cache.get((1,)))

    def test_expiry_does_not_extend_on_read(self):
        cache = ScoreCache(ttl=10)
        with mock.patch('app.services.score_cache.time.monotonic', return_value=0):
            cache.put((1,), score_pdf.ParsedScore())
        with mock.patch('app.services.score_cache.time.monotonic', return_value=9):
            self.assertIsNotNone(cache.get((1,)))
        with mock.patch('app.services.score_cache.time.monotonic', return_value=10):
            self.assertIsNone(cache.get((1,)))
        self.assertEqual(cache._bytes, 0)

    def test_cached_pdf_avoids_decode_and_preserves_limits_and_mutation_isolation(self):
        data = build_vector_score_pdf()
        with mock.patch.object(score_pdf, '_score_cache', ScoreCache()), \
                mock.patch.object(score_pdf.pdfplumber, 'open', wraps=score_pdf.pdfplumber.open) as decode:
            original = score_pdf.parse_vector_score(data)
            self.assertEqual(score_pdf.parse_vector_score(data), original)
            self.assertEqual(decode.call_count, 1)
            original.measures.clear()
            self.assertTrue(score_pdf.parse_vector_score(data).measures)
            score_pdf.parse_vector_score(data, max_measures=1)
            self.assertEqual(decode.call_count, 2)
            score_pdf.parse_vector_score(data, use_cache=False)
            self.assertEqual(decode.call_count, 3)
            with self.assertRaises(score_pdf.ScorePDFError):
                score_pdf.parse_vector_score(data, max_pages=0)
            with self.assertRaises(score_pdf.ScorePDFError):
                score_pdf.parse_vector_score(b'bad')

    def test_failed_decodes_are_not_cached(self):
        with mock.patch.object(score_pdf, '_score_cache', ScoreCache()), \
                mock.patch.object(score_pdf.pdfplumber, 'open', side_effect=ValueError('bad')) as decode:
            for _ in range(2):
                with self.assertRaises(score_pdf.ScorePDFError):
                    score_pdf.parse_vector_score(b'%PDF-invalid')
            self.assertEqual(decode.call_count, 2)
