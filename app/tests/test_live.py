import time
from threading import Event
import unittest
import numpy as np
from app.capture.live import TextCollector, LiveCapture
from app.capture.screen import Region


class CollectorTests(unittest.TestCase):
    def accept(self, collector, text):
        collector.observe(text)
        return collector.observe(text)

    def test_stable_changes_and_duplicate_suppression(self):
        c = TextCollector()
        self.assertIsNone(c.observe('Transient OCR error'))
        self.assertIsNone(c.observe('Hello'))
        self.assertEqual(c.observe('Hello'), 'Hello')
        self.assertIsNone(c.observe('Hello'))
        self.assertEqual(self.accept(c, 'Next prompt'), 'Hello\nNext prompt')

    def test_growing_prompt_extends_instead_of_duplicating(self):
        c = TextCollector()
        self.assertEqual(self.accept(c, 'The\n'), 'The')
        self.assertEqual(self.accept(c, 'The quick\n'), 'The quick')
        self.assertEqual(self.accept(c, 'The quick brown fox\n'), 'The quick brown fox')

    def test_blank_separates_repeated_prompts(self):
        c = TextCollector()
        self.accept(c, 'Again')
        self.assertIsNone(self.accept(c, ''))
        self.assertEqual(self.accept(c, 'Again'), 'Again\nAgain')

    def test_latest_mode_and_internal_whitespace(self):
        c = TextCollector('Latest text')
        self.assertEqual(self.accept(c, 'First,  WORD!\nNext line.\n'), 'First,  WORD!\nNext line.')
        self.assertEqual(self.accept(c, 'Replacement'), 'Replacement')
        self.assertEqual(self.accept(c, ''), '')


class LiveCaptureTests(unittest.TestCase):
    def session(self, **kwargs):
        live = LiveCapture(Region(0, 0, 10, 10), interval=.1, **kwargs)
        def cleanup():
            live.stop()
            for thread in live.threads:
                thread.join(1)
        self.addCleanup(cleanup)
        return live

    def test_background_updates(self):
        live = self.session(capture=lambda r: np.zeros((10, 10, 4), dtype=np.uint8), ocr=lambda frame, exe: 'Hello\n')
        live.start()
        self.assertEqual(live.updates.get(timeout=1), ('reading', (1, 'Hello')))
        self.assertEqual(live.updates.get(timeout=1), ('text', 'Hello'))
        time.sleep(.15)
        self.assertTrue(live.updates.empty())

    def test_preview_continues_during_slow_ocr_and_stop_discards_result(self):
        blocked, release = Event(), Event()
        captured = []
        def capture(region):
            captured.append(1)
            return np.zeros((10, 10, 4), dtype=np.uint8)
        def ocr(frame, executable):
            blocked.set()
            release.wait(2)
            return 'Late text'
        live = self.session(capture=capture, ocr=ocr)
        self.addCleanup(release.set)
        live.start()
        self.assertTrue(blocked.wait(1))
        time.sleep(.25)
        self.assertGreaterEqual(len(captured), 2)
        self.assertEqual(live.previews.qsize(), 1)
        live.stop()
        release.set()
        for thread in live.threads:
            thread.join(1)
        self.assertTrue(live.updates.empty())

    def test_capture_failure_retries_without_stopping(self):
        def broken(region):
            raise RuntimeError('Capture failed')
        live = self.session(capture=broken)
        live.start()
        self.assertEqual(live.updates.get(timeout=1), ('warning', 'Capture failed'))
        self.assertFalse(live.stop_event.is_set())
        self.assertEqual(live.updates.get(timeout=2), ('warning', 'Capture failed'))

    def test_invalid_interval(self):
        for value in (0, .01, float('nan')):
            with self.assertRaises(ValueError):
                LiveCapture(Region(0, 0, 10, 10), interval=value)
