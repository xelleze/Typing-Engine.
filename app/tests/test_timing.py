import unittest
import numpy as np
from app.config.typing_profile import TypingProfile
from app.typing.timing_engine import TimingEngine
from app.typing.rhythm_model import RhythmModel


class TimingTests(unittest.TestCase):
    def test_seeded_and_preserves_text(self):
        text = 'The extraordinarily uncommon terminology surprised everyone.\nA naïve test!  42\t🙂'
        engine = TimingEngine(seed=42)
        self.assertEqual(engine.generate(text), engine.generate(text))
        self.assertEqual(''.join(k.char for k in engine.generate(text)), text)

    def test_exact_wpm_and_cognitive_caps(self):
        text = 'The extraordinarily uncommon terminology surprised everyone.'
        for wpm in (1, 55, 110, 250):
            rows = TimingEngine(TypingProfile(target_wpm=wpm), seed=3).explain(text)
            total = sum(r['final_delay'] for r in rows)
            self.assertAlmostEqual(len(text) / 5 * 60000 / total, wpm)
            self.assertTrue(all(r['final_cognitive_ms'] <= 450 for r in rows))
            self.assertTrue(all(r['final_delay'] > 0 for r in rows))

    def test_rare_planning_is_at_word_start(self):
        rows = TimingEngine(seed=5).explain('onychophora')
        self.assertGreater(rows[0]['planning_delay'], 50)
        self.assertTrue(all(r['planning_delay'] == 0 for r in rows[1:]))
        self.assertGreater(rows[0]['cognitive_ms'], sum(r['cognitive_ms'] for r in rows[1:]))

    def test_chunks_reduce_motor_difficulty(self):
        plain = TypingProfile(chunk_skill=0, transition_variance=0, rhythm_variance=0)
        skilled = TypingProfile(chunk_skill=1, transition_variance=0, rhythm_variance=0)
        a = TimingEngine(plain, seed=1).explain('the')
        b = TimingEngine(skilled, seed=1).explain('the')
        self.assertLess(b[1]['motor_ms'], a[1]['motor_ms'])
        self.assertLess(b[2]['motor_ms'], a[2]['motor_ms'])

    def test_tempo_is_correlated(self):
        rhythm = RhythmModel(np.random.default_rng(42))
        values = np.array([rhythm.step() for _ in range(5000)])
        self.assertGreater(np.corrcoef(values[:-1], values[1:])[0, 1], .85)

    def test_punctuation_pause_follows_emission(self):
        rows = TimingEngine(seed=1).explain('the;the\none')
        self.assertEqual(rows[3]['boundary_delay'], 0)
        self.assertEqual(rows[4]['boundary_delay'], 60)
        self.assertEqual(rows[8]['boundary_delay'], 180)

    def test_unseeded_explanation_matches_timeline(self):
        engine = TimingEngine()
        timeline = engine.generate('An unseeded example.')
        rows = engine.explain('An unseeded example.')
        self.assertEqual([k.delay_ms for k in timeline], [r['final_delay'] for r in rows])

    def test_empty_and_invalid(self):
        self.assertEqual(TimingEngine().generate(''), [])
        with self.assertRaises(ValueError):
            TypingProfile(target_wpm=0)
        with self.assertRaises(ValueError):
            TypingProfile(target_wpm=float('nan'))
