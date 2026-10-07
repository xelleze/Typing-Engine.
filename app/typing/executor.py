"""Interruptible playback of an immutable snapshot of precomputed keystrokes."""
from threading import Condition, Thread
from time import monotonic
from math import isfinite
from typing import Callable
from collections import deque
from .timing_engine import Keystroke


class PynputOutput:
    def __init__(self):
        from pynput.keyboard import Controller, Key
        self.controller = Controller()
        self.special = {'\n': Key.enter, '\t': Key.tab, '\b': Key.backspace}

    def emit(self, char: str):
        if char in self.special:
            key = self.special[char]
            try:
                self.controller.press(key)
            finally:
                self.controller.release(key)
        else:
            self.controller.type(char)


class KeyboardExecutor:
    def __init__(self, output=None, hotkeys: bool = True,
                 on_progress: Callable[[int, int], None] | None = None):
        self.output = output
        self.hotkeys = hotkeys
        self.on_progress = on_progress
        self._condition = Condition()
        self._thread = None
        self._listener = None
        self.state = 'idle'
        self.error: str | None = None
        self.completed = 0
        self.total = 0
        self._paused = False
        self._cancelled = False
        self._pending = deque()
        self._keep_open = False

    def start(self, timeline: list[Keystroke], countdown_seconds: float = 3., keep_open: bool = False) -> None:
        if not isinstance(timeline, list) or not all(isinstance(k, Keystroke) for k in timeline):
            raise TypeError('Executor accepts only a list of Keystroke objects')
        if not isfinite(countdown_seconds) or countdown_seconds < 0:
            raise ValueError('Countdown must be finite and nonnegative')
        with self._condition:
            if self._thread and self._thread.is_alive():
                raise RuntimeError('Playback is already active')
            # Install controls before the countdown and before any key emission.
            if self.output is None:
                self.output = PynputOutput()
            if self.hotkeys and self._listener is None:
                from pynput.keyboard import GlobalHotKeys
                self._listener = GlobalHotKeys({
                    '<ctrl>+<alt>+<esc>': self.emergency_stop,
                    '<ctrl>+<alt>+p': self.toggle_pause,
                })
                self._listener.start()
                self._listener.wait()
            self._cancelled = self._paused = False
            self._pending = deque(timeline)
            self._keep_open = keep_open
            self.completed, self.total, self.error = 0, len(timeline), None
            self.state = 'countdown' if countdown_seconds else 'running'
            self._thread = Thread(target=self._run, args=(countdown_seconds,), daemon=True)
            self._thread.start()

    def append(self, timeline: list[Keystroke]):
        if not isinstance(timeline, list) or not all(isinstance(k, Keystroke) for k in timeline):
            raise TypeError('Executor accepts only a list of Keystroke objects')
        with self._condition:
            if not self._keep_open or self._cancelled or self.state in ('error', 'completed', 'cancelled', 'idle'):
                raise RuntimeError('No open playback session')
            self._pending.extend(timeline)
            self.total += len(timeline)
            self._condition.notify_all()

    def _wait(self, seconds: float) -> bool:
        remaining = seconds
        with self._condition:
            while remaining > 0 or self._paused:
                if self._cancelled:
                    return False
                if self._paused:
                    self._condition.wait()
                    continue
                started = monotonic()
                self._condition.wait(timeout=remaining)
                remaining = max(0., remaining - (monotonic() - started))
            return not self._cancelled

    def _run(self, countdown: float):
        try:
            if not self._wait(countdown):
                return
            with self._condition:
                self.state = 'paused' if self._paused else 'running'
            # Absolute active-time deadlines prevent output overhead accumulating.
            # Paused time is excluded by _wait; emission time reduces the next wait.
            overhead = 0.
            while True:
                with self._condition:
                    while (not self._pending or self._paused) and not self._cancelled:
                        if not self._pending and not self._keep_open:
                            return
                        if not self._paused:
                            self.state = 'waiting'
                        overhead = 0.
                        self._condition.wait()
                    if self._cancelled:
                        return
                    self.state = 'running'
                    stroke = self._pending.popleft()
                if not self._wait(max(0., stroke.delay_ms / 1000 - overhead)):
                    return
                with self._condition:
                    # Pause/cancel may arrive between wait and acquiring this lock.
                    while self._paused and not self._cancelled:
                        self._condition.wait()
                    if self._cancelled:
                        return
                    started = monotonic()
                    try:
                        self.output.emit(stroke.char)
                    except Exception as exc:
                        if not self._keep_open:
                            raise
                        self.error = str(exc)
                        self._pending.appendleft(stroke)
                        self._paused = True
                        self._resume_state = 'running'
                        self.state = 'paused'
                        continue
                    self.completed += 1
                    overhead = max(0., overhead - stroke.delay_ms / 1000) + monotonic() - started
                if self.on_progress:
                    self.on_progress(self.completed, self.total)
        except Exception as exc:
            with self._condition:
                self.error = str(exc)
                self.state = 'error'
        finally:
            with self._condition:
                if self.state != 'error':
                    self.state = 'cancelled' if self._cancelled else 'completed'
                self._condition.notify_all()

    def pause(self):
        with self._condition:
            if self.state in ('running', 'countdown', 'waiting'):
                self._resume_state = self.state
                self._paused = True
                self.state = 'paused'
                self._condition.notify_all()

    def resume(self):
        with self._condition:
            if self._paused:
                self.error = None
                self._paused = False
                self.state = self._resume_state
                self._condition.notify_all()

    def toggle_pause(self):
        with self._condition:
            self.resume() if self._paused else self.pause()

    def cancel(self):
        with self._condition:
            self._cancelled = True
            self._condition.notify_all()

    def emergency_stop(self):
        self.cancel()

    def join(self, timeout: float | None = None):
        if self._thread:
            self._thread.join(timeout)

    def close(self):
        self.cancel()
        self.join(1.)
        if self._listener:
            self._listener.stop()
            self._listener = None
