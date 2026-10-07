import time
import unittest
from app.typing.executor import KeyboardExecutor
from app.typing.timing_engine import Keystroke


class Output:
    def __init__(self):
        self.chars = []
    def emit(self, char):
        self.chars.append(char)


class ExecutorTests(unittest.TestCase):
    def test_output_and_snapshot(self):
        out = Output()
        executor = KeyboardExecutor(out, hotkeys=False)
        timeline = [Keystroke('a', 10), Keystroke('\n', 10)]
        executor.start(timeline, 0)
        timeline.clear()
        executor.join(1)
        self.assertEqual(out.chars, ['a', '\n'])
        self.assertEqual(executor.state, 'completed')

    def test_cancel_interrupts_countdown(self):
        out = Output()
        executor = KeyboardExecutor(out, hotkeys=False)
        executor.start([Keystroke('a', 1000)], 10)
        executor.emergency_stop()
        executor.join(.5)
        self.assertEqual(executor.state, 'cancelled')
        self.assertEqual(out.chars, [])

    def test_pause_preserves_remaining_delay(self):
        out = Output()
        executor = KeyboardExecutor(out, hotkeys=False)
        executor.start([Keystroke('a', 180)], 0)
        time.sleep(.02)
        executor.pause()
        time.sleep(.2)
        self.assertEqual(out.chars, [])
        executor.resume()
        time.sleep(.02)
        self.assertEqual(out.chars, [])
        executor.join(1)
        self.assertEqual(out.chars, ['a'])

    def test_failure_is_reported(self):
        class Broken:
            def emit(self, char):
                raise RuntimeError('output failed')
        executor = KeyboardExecutor(Broken(), hotkeys=False)
        executor.start([Keystroke('a', 0)], 0)
        executor.join(1)
        self.assertEqual(executor.state, 'error')
        self.assertEqual(executor.error, 'output failed')
