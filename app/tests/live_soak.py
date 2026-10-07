"""Real 60-second reactive OCR test; keyboard events are always simulated.

python -m app.tests.live_soak --label before
"""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import time
import tkinter as tk
from tkinter import font
import cv2
from app.gui import TypingApp
from app.capture.screen import Region, capture_region
from app.typing.executor import KeyboardExecutor

# Intentionally repeat an article at a page boundary: two legitimate words
# must not be mistaken for one overlapping word from a scrolling viewport.
PAGES = [
    'The old oak tree stood at the edge of the meadow for longer than anyone could remember. Its massive branches sheltered wandering birds.',
    'A quiet stream wound through the village while people walked slowly beside the water and listened to stories about the',
    'The garden was a masterpiece of color and life an oasis hidden away from the noise of the outside world.',
    'The morning light reached every flower. Children followed narrow paths and found butterflies resting beside a wooden bench in the garden.',
    'Garden paths led toward a small pond where bright fish moved beneath the surface and reflected the clouds passing across the sky.',
    'Beyond the pond a painter worked quietly beneath an apple tree. She mixed warm colors and carefully painted the distant rolling hills.',
    'The afternoon breeze carried the scent of fresh bread from the kitchen. Everyone gathered around the table and shared stories about their day.',
    'Later the sky turned orange and the birds returned to their nests. The last visitors closed the gate and followed the road home.',
    'Night arrived softly over the peaceful village. Small lights appeared in every window while the river continued its gentle journey toward the sea.',
    'The following morning brought another clear sky. A gardener opened the gate and welcomed new visitors to the flowers beside the old oak tree.',
]


class ReactiveOutput:
    def __init__(self):
        self.expected = ' '.join(PAGES) + ' '
        self.chars = []
        self.mismatches = []
        self.position = 0
        self.lock = Lock()
        self.started = None

    def emit(self, char):
        with self.lock:
            self.chars.append(char)
            expected = self.expected[self.position:self.position + 1]
            if char != expected:
                if len(self.mismatches) < 30:
                    self.mismatches.append({'seconds': round(time.monotonic() - self.started, 3),
                        'position': self.position, 'expected': expected, 'actual': char,
                        'context': self.expected[max(0, self.position - 20):self.position + 35]})
                return
            self.position += 1

    def snapshot(self):
        with self.lock:
            return self.position, ''.join(self.chars), list(self.mismatches)


def run(duration, label):
    with TemporaryDirectory() as directory:
        root = tk.Tk()
        app = TypingApp(root, Path(directory) / 'words.sqlite')
        app.error_percent.set('0')
        root.withdraw()
        source = tk.Tk()
        source.title('60-second changing typing test — simulated output')
        source.geometry('920x265+30+30')
        source.attributes('-topmost', True)
        canvas = tk.Canvas(source, bg='#fafafa', highlightthickness=0, height=205)
        canvas.pack(fill='both', expand=True)
        caption = tk.Label(source, text='', bg='#fafafa', anchor='w')
        caption.pack(fill='x')
        face = font.Font(root=source, family='Consolas', size=21)
        output = ReactiveOutput()
        app.executor = KeyboardExecutor(output, hotkeys=False)
        boundaries = []
        offset = 0
        for page in PAGES:
            boundaries.append(offset)
            offset += len(page) + 1
        readings, last_revision, last_render = [], 0, None
        def render(page_index, position):
            canvas.delete('all')
            x, y, word_offset = 18, 20, boundaries[page_index]
            for word in PAGES[page_index].split():
                width = face.measure(word + ' ')
                if x + width > 900:
                    x, y = 18, y + 42
                active = word_offset <= position < word_offset + len(word) + 1
                canvas.create_text(x, y, text=word, font=face, anchor='nw', fill='#28665f' if active else '#555960')
                if active:
                    canvas.create_line(x, y + 33, x + face.measure(word), y + 33, fill='#28665f', width=2)
                x += width
                word_offset += len(word) + 1
        try:
            render(0, 0)
            root.update()
            source.update()
            app.region = Region(canvas.winfo_rootx(), canvas.winfo_rooty(), canvas.winfo_width(), canvas.winfo_height())
            app.region_overlaps_window = lambda: False
            app.live_mode.set('Latest text')
            app.live_interval.set('0.5')
            app.wpm.set('180')
            app.countdown.set('0')
            app.start_live()
            warmup = time.monotonic() + 5
            while time.monotonic() < warmup:
                root.update()
                source.update()
                if app.live.collector.accepted:
                    break
                time.sleep(.01)
            assert app.live and app.live.collector.accepted, 'No initial OCR reading'
            output.started = time.monotonic()
            app.start()
            deadline = output.started + duration
            next_log = output.started + 10
            last_page = 0
            while time.monotonic() < deadline:
                position, actual, mismatches = output.snapshot()
                page_index = max(i for i, boundary in enumerate(boundaries) if position >= boundary)
                if (page_index, position) != last_render:
                    render(page_index, position)
                    last_render = (page_index, position)
                last_page = page_index
                caption.configure(text=f'{duration - (time.monotonic() - output.started):.0f}s remaining · page {page_index + 1} · correct characters {position}')
                root.update()
                source.update()
                if app.live and app.live.revision != last_revision:
                    last_revision = app.live.revision
                    readings.append({'seconds': round(time.monotonic() - output.started, 3),
                                     'revision': last_revision, 'text': app.live.collector.accepted})
                if time.monotonic() >= next_log:
                    print(f'{time.monotonic() - output.started:.0f}s: page {page_index + 1}, {position} correct chars, {len(mismatches)} recorded mismatches, state {app.executor.state}', flush=True)
                    next_log += 10
                time.sleep(.01)
            position, actual, mismatches = output.snapshot()
            before_stop = app.executor.state
            artifacts = Path('artifacts')
            artifacts.mkdir(exist_ok=True)
            cv2.imwrite(str(artifacts / f'live-soak-{label}.png'), capture_region(app.region))
            app.executor.cancel()
            app.executor.join(1)
            report = {'duration_seconds': round(time.monotonic() - output.started, 3),
                      'wpm': 180, 'ocr_interval': .5, 'mode': 'Latest text',
                      'pages_reached': last_page + 1, 'correct_characters': position,
                      'typed_characters': len(actual), 'mismatches': mismatches,
                      'state_before_stop': before_stop, 'state_after_stop': app.executor.state,
                      'actual': actual, 'expected_prefix': output.expected[:len(actual)], 'readings': readings}
            path = artifacts / f'live-soak-{label}.json'
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'Report: {path}; pages reached: {last_page + 1}; mismatches: {len(mismatches)}', flush=True)
            assert not mismatches, f'Typing diverged: {mismatches[0]}'
            assert last_page >= 3, 'Test did not progress past the first three pages'
            assert actual == output.expected[:len(actual)], 'Output contains missing or duplicated words'
            assert before_stop in ('running', 'waiting'), 'Session ended before explicit stop'
            assert app.executor.state == 'cancelled'
        finally:
            app.close()
            source.destroy()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--label', default='check')
    args = parser.parse_args()
    run(args.duration, args.label)
