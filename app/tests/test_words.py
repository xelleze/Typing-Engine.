import unittest
from app.config.typing_profile import TypingProfile
from app.typing.word_model import analyze_word, chunk_at


class WordTests(unittest.TestCase):
    def test_length_does_not_penalize_common_words(self):
        common = analyze_word('something', 0, TypingProfile())
        rare = analyze_word('onychophora', 0, TypingProfile())
        self.assertLess(common.planning_ms, 8)
        self.assertGreater(rare.planning_ms, 50)

    def test_chunk_entry_has_no_bonus(self):
        self.assertEqual(chunk_at('the', 0), ('', 0.))
        self.assertLess(chunk_at('the', 1)[1], 0)

    def test_adaptation_reduces_only_planning(self):
        class Store:
            def seen_count(self, word):
                return 50
        first = analyze_word('onychophora', 0, TypingProfile())
        learned = analyze_word('onychophora', 0, TypingProfile(), Store())
        self.assertLess(learned.planning_ms, first.planning_ms / 10)
