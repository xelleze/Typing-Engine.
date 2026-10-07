import time
import unittest
from app.typing.executor import KeyboardExecutor
from app.typing.timing_engine import Keystroke
from app.typing.stream_text import StreamTextPlanner


class StreamTests(unittest.TestCase):
    def test_growing_and_scrolling_prompts(self):
        planner = StreamTextPlanner('The old oak tree')
        self.assertEqual(planner.observe('The old oak tree had stood'), 'had stood ')
        self.assertEqual(planner.observe('oak tree had stood at the edge'), 'at the edge ')
        self.assertEqual(planner.observe('at the edge'), '')
        self.assertEqual(planner.observe('at the edge of the meadow'), 'of the meadow ')

    def test_duplicate_blank_and_ocr_corrections(self):
        p = StreamTextPlanner('The old oak tree had stood at the edge')
        self.assertEqual(p.observe(''), '')
        self.assertEqual(p.observe('The old oak tree had stood at the edge'), '')
        self.assertEqual(p.observe('The old oak tree had stood at the Edge'), '')
        self.assertEqual(p.observe('The old oak free had stood at the edge'), '')
        self.assertEqual(p.observe('The old oak tree had stood at the edge of the meadow'), 'of the meadow ')

    def test_unrelated_prompt_and_wrapping(self):
        p = StreamTextPlanner('First prompt')
        self.assertEqual(p.observe('Another\nnew prompt'), 'Another new prompt ')
        self.assertEqual(p.observe('Another\nnew prompt'), '')

    def test_new_page_does_not_lose_repeated_article(self):
        p = StreamTextPlanner('A quiet stream wound through the village and people listened to stories about the')
        page = 'The garden was a masterpiece of color and life an oasis hidden away from the noise of the outside world.'
        self.assertEqual(p.observe(page), page + ' ')

    def test_scrolling_overlap_survives_one_ocr_error(self):
        p = StreamTextPlanner('The garden was a masterpiece of color and life an oasis hidden away from the noise of the outside world')
        page = 'color and life an oasis hldden away from the noise of the outside world where birds sang softly'
        self.assertEqual(p.observe(page), 'where birds sang softly ')

    def test_growing_prompt_starts_with_one_word(self):
        p = StreamTextPlanner('The')
        self.assertEqual(p.observe('The garden was quiet'), 'garden was quiet ')

    def executor(self, output):
        executor = KeyboardExecutor(output, hotkeys=False)
        self.addCleanup(executor.close)
        return executor

    def wait_for(self, predicate):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not predicate():
            time.sleep(.005)
        self.assertTrue(predicate())

    def test_waiting_session_resumes_and_only_cancel_ends(self):
        class Output:
            chars = []
            def emit(self, char):
                self.chars.append(char)
        out = Output()
        executor = self.executor(out)
        executor.start([Keystroke('a', 5)], 0, keep_open=True)
        self.wait_for(lambda: executor.state == 'waiting')
        self.assertEqual(out.chars, ['a'])
        executor.append([Keystroke('b', 5)])
        self.wait_for(lambda: executor.completed == 2 and executor.state == 'waiting')
        time.sleep(.05)
        self.assertEqual(executor.state, 'waiting')
        executor.emergency_stop()
        executor.join(.5)
        self.assertEqual(executor.state, 'cancelled')
        with self.assertRaises(RuntimeError):
            executor.append([Keystroke('c', 5)])

    def test_empty_start_pause_and_resume_while_waiting(self):
        class Output:
            chars = []
            def emit(self, char):
                self.chars.append(char)
        out = Output()
        executor = self.executor(out)
        executor.start([], 0, keep_open=True)
        self.wait_for(lambda: executor.state == 'waiting')
        executor.pause()
        executor.append([Keystroke('x', 5)])
        time.sleep(.05)
        self.assertEqual(out.chars, [])
        executor.resume()
        self.wait_for(lambda: out.chars == ['x'])
        executor.close()
        self.assertEqual(executor.state, 'cancelled')

    def test_output_failure_pauses_open_session_for_retry(self):
        class Output:
            broken = True
            chars = []
            def emit(self, char):
                if self.broken:
                    raise RuntimeError('temporarily unavailable')
                self.chars.append(char)
        out = Output()
        executor = self.executor(out)
        executor.start([Keystroke('x', 5)], 0, keep_open=True)
        self.wait_for(lambda: executor.state == 'paused')
        self.assertEqual(executor.completed, 0)
        self.assertIn('temporarily', executor.error)
        out.broken = False
        executor.resume()
        self.wait_for(lambda: out.chars == ['x'])
        self.assertIsNone(executor.error)
