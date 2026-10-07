"""Continuous preview and serial OCR, independent of keyboard playback."""
from math import isfinite
from queue import Queue, Empty, Full
from threading import Event, Lock, Thread
from time import monotonic
from .screen import capture_region
from .ocr import recognize


class TextCollector:
    """Accept stable readings; extend growing prompts without duplicating prefixes."""
    def __init__(self, mode='Collect changes', stable_readings=2):
        if mode not in ('Collect changes', 'Latest text'):
            raise ValueError('Unknown capture mode')
        self.mode = mode
        self.stable_readings = stable_readings
        self.candidate = None
        self.count = 0
        self.accepted = None
        self.segments = []
        self.new_segment = True

    def observe(self, text):
        # Tesseract appends a terminal newline even for single-line prompts.
        text = text.rstrip('\n')
        if text == self.candidate:
            self.count += 1
        else:
            self.candidate, self.count = text, 1
        if self.count < self.stable_readings or text == self.accepted:
            return None
        previous = self.accepted
        self.accepted = text
        if not text.strip():
            self.new_segment = True
            return '' if self.mode == 'Latest text' else None
        if self.mode == 'Latest text':
            return text
        if not self.new_segment and previous and text.startswith(previous):
            self.segments[-1] = text
        else:
            self.segments.append(text)
        self.new_segment = False
        return '\n'.join(self.segments)


class LiveCapture:
    def __init__(self, region, interval=.5, mode='Collect changes', executable=None,
                 capture=capture_region, ocr=recognize):
        if not isfinite(interval) or interval < .1:
            raise ValueError('OCR interval must be at least 0.1 seconds')
        self.region, self.interval, self.executable = region, interval, executable
        self.capture, self.ocr = capture, ocr
        self.collector = TextCollector(mode)
        self.stop_event = Event()
        self.suspended = Event()
        self.ready = Event()
        self.lock = Lock()
        self.revision = 0
        self.frame = None
        self.previews = Queue(maxsize=1)
        self.updates = Queue(maxsize=64)
        self.threads = []

    def start(self):
        if self.threads:
            raise RuntimeError('Create a new live session before restarting')
        self.threads = [Thread(target=self._capture_loop, daemon=True),
                        Thread(target=self._ocr_loop, daemon=True)]
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stop_event.set()
        self.ready.set()

    def _error(self, exc):
        self.stop()
        try:
            self.updates.put_nowait(('error', str(exc)))
        except Full:
            # Preserve a visible failure rather than silently dropping OCR text.
            while not self.updates.empty():
                try:
                    self.updates.get_nowait()
                except Empty:
                    break
            self.updates.put_nowait(('error', 'Live capture stopped: review updates were not consumed.'))

    def _capture_loop(self):
        while not self.stop_event.is_set():
            try:
                if self.suspended.is_set():
                    self.stop_event.wait(.1)
                    continue
                frame = self.capture(self.region)
                if self.stop_event.is_set():
                    return
                with self.lock:
                    self.frame = frame
                self.ready.set()
                try:
                    self.previews.get_nowait()
                except Empty:
                    pass
                self.previews.put_nowait(frame)
                self.stop_event.wait(.1)
            except Exception as exc:
                self._warning(exc)
                self.stop_event.wait(1.)

    def _warning(self, exc):
        try:
            self.updates.put_nowait(('warning', str(exc)))
        except Full:
            pass

    def _publish(self, item):
        while not self.stop_event.is_set():
            try:
                self.updates.put(item, timeout=.1)
                return
            except Full:
                continue

    def _ocr_loop(self):
        self.ready.wait()
        while not self.stop_event.is_set():
            try:
                if self.suspended.is_set():
                    self.stop_event.wait(.1)
                    continue
                started = monotonic()
                with self.lock:
                    frame = self.frame
                if frame is None:
                    return
                text = self.ocr(frame, self.executable)
                if self.stop_event.is_set():
                    return
                with self.lock:
                    previous = self.collector.accepted
                    collected = self.collector.observe(text)
                    changed = self.collector.accepted != previous
                    if changed:
                        self.revision += 1
                    reading = (self.revision, self.collector.accepted)
                if changed:
                    self._publish(('reading', reading))
                if collected is not None:
                    self._publish(('text', collected))
                self.stop_event.wait(max(.01, self.interval - (monotonic() - started)))
            except Exception as exc:
                self._warning(exc)
                self.stop_event.wait(1.)
