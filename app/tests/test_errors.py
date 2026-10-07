import unittest
from unittest.mock import Mock
from math import hypot
from app.typing.error_model import ErrorModel
from app.typing.timing_engine import TimingEngine
from app.typing.executor import PynputOutput
from app.typing.keyboard_layout import get_key


def visible(rows):
    result = []
    for row in rows:
        if row['char'] == '\b':
            result.pop()
        else:
            result.append(row['char'])
    return ''.join(result)


class ErrorTests(unittest.TestCase):
    def test_corrected_text_and_target_duration(self):
        text = 'The garden was beautiful, with flowers everywhere.\n123!'
        original = TimingEngine(seed=42).explain(text)
        planned = ErrorModel(rate=1, seed=42).plan(original)
        self.assertEqual(visible(planned), text)
        self.assertEqual(planned[-1]['source_progress'], len(text))
        self.assertAlmostEqual(sum(r['final_delay'] for r in planned), sum(r['final_delay'] for r in original))
        errors = [i for i, r in enumerate(planned) if r['event'] == 'typo']
        self.assertGreater(len(errors), 3)
        for index in errors:
            self.assertEqual(planned[index + 1]['char'], '\b')
            self.assertEqual(planned[index + 2]['event'], 'correction')
            self.assertEqual(planned[index + 2]['char'], planned[index]['intended_char'])
            a, b = get_key(planned[index]['char']), get_key(planned[index]['intended_char'])
            self.assertLessEqual(hypot(a.x - b.x, a.y - b.y), 1.5)

    def test_seed_reproducibility_and_zero_rate(self):
        rows = TimingEngine(seed=1).explain('A garden filled with flowers.')
        self.assertEqual(ErrorModel(rate=.5, seed=3).plan(rows), ErrorModel(rate=.5, seed=3).plan(rows))
        zero = ErrorModel(rate=0, seed=3).plan(rows)
        self.assertEqual(''.join(r['char'] for r in zero), ''.join(r['char'] for r in rows))
        self.assertEqual([r['final_delay'] for r in zero], [r['final_delay'] for r in rows])

    def test_small_rate(self):
        rows = TimingEngine(seed=42).explain('garden ' * 2000)
        planned = ErrorModel(rate=.005, seed=7).plan(rows)
        rate = sum(r['event'] == 'typo' for r in planned) / 12000
        self.assertGreater(rate, .002)
        self.assertLess(rate, .009)

    def test_continued_rng_across_batches(self):
        rows = TimingEngine(seed=1).explain('garden flowers meadow quiet stream ' * 10)
        model = ErrorModel(rate=.1, seed=42)
        first, second = model.plan(rows), model.plan(rows)
        self.assertNotEqual(first, second)
        self.assertEqual(visible(first), visible(second))

    def test_optional_uncorrected_errors(self):
        rows = TimingEngine(seed=1).explain('garden flowers')
        planned = ErrorModel(rate=1, correct=False, seed=1).plan(rows)
        self.assertNotEqual(visible(planned), 'garden flowers')
        self.assertFalse(any(r['char'] == '\b' for r in planned))

    def test_progress_does_not_count_extra_keys_as_source_text(self):
        rows = TimingEngine(seed=1).explain('garden')
        planned = ErrorModel(rate=1, seed=1).plan(rows)
        for i, row in enumerate(planned):
            if row['event'] == 'typo':
                self.assertEqual(row['source_progress'], planned[i + 1]['source_progress'])
                self.assertEqual(planned[i + 2]['source_progress'], row['source_progress'] + 1)

    def test_real_backspace_adapter(self):
        output = PynputOutput.__new__(PynputOutput)
        backspace = object()
        output.special = {'\b': backspace}
        output.controller = Mock()
        output.emit('\b')
        output.controller.press.assert_called_once_with(backspace)
        output.controller.release.assert_called_once_with(backspace)
        output.controller.type.assert_not_called()

    def test_invalid_rate(self):
        for value in (-.1, 1.1, float('nan')):
            with self.assertRaises(ValueError):
                ErrorModel(value)
