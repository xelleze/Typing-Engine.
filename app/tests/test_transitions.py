import unittest
from app.typing.transition_model import transition, TRANSITION_MATRIX


class TransitionTests(unittest.TestCase):
    def test_alternation(self):
        self.assertLess(transition("f", "j").score, transition("a", "f").score)

    def test_same_finger(self):
        self.assertGreater(transition("f", "r").score, transition("f", "d").score)

    def test_repeats_and_shift(self):
        self.assertTrue(transition("f", "f").repeated_key)
        self.assertGreater(transition("f", "f").score, transition("f", "d").score)
        self.assertGreater(transition("f", "J").score, transition("f", "j").score)

    def test_cache_and_bounds(self):
        self.assertIs(transition("t", "h"), TRANSITION_MATRIX["t", "h"])
        self.assertTrue(all(.55 <= t.score <= 2.25 for t in TRANSITION_MATRIX.values()))
